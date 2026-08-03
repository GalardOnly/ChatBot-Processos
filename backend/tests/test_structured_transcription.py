from preparador_audiencia.repositories import ChunkRecord
from preparador_audiencia.structured_transcription import (
    build_structured_transcription,
)


def _chunk(
    page: int,
    index: int,
    text: str,
    confidence: str = "media",
) -> ChunkRecord:
    return ChunkRecord(
        id=page * 10 + index,
        processo_id="proc_1",
        page_number=page,
        chunk_index=index,
        text=text,
        document_type=None,
        source_confidence=confidence,
        vector_id=None,
        created_at="2026-08-03T00:00:00+00:00",
    )


def test_builds_integral_testimony_without_repeating_chunk_overlap() -> None:
    chunks = [
        _chunk(
            10,
            0,
            "POLICIA CIVIL\nTERMO DE DEPOIMENTO EM AUTO DE PRISAO EM FLAGRANTE "
            "QUE PRESTA A TESTEMUNHA: MARIA DA SILVA\nINQUERITO 123\n"
            "DISSE QUE presenciou os fatos. trecho compartilhado",
        ),
        _chunk(10, 1, "trecho compartilhado\nPag. 1 de 2"),
        _chunk(
            11,
            0,
            "A testemunha confirmou o horario. Nada mais disse nem lhe foi perguntado. "
            "Pag. 2 de 2",
        ),
    ]

    result = build_structured_transcription(chunks)

    assert result.status == "concluido"
    assert len(result.testimonies) == 1
    testimony = result.testimonies[0]
    assert testimony["pessoa"] == "MARIA DA SILVA"
    assert testimony["papel"] == "testemunha"
    assert testimony["fase"] == "inquerito"
    assert testimony["cobertura"] == "integral"
    assert testimony["pagina_inicial"] == 10
    assert testimony["pagina_final"] == 11
    assert testimony["texto_consolidado"].count("trecho compartilhado") == 1
    assert testimony["revisao_necessaria"] is False


def test_marks_glued_ocr_for_review_without_rewriting_text() -> None:
    glued = " ".join(
        [
            "palavrasefrasescoladasemumtokenmuitogrande",
            "outrotrechocoladoquenãodevesercorrigidoautomaticamente",
            "terceiroblocosemespacosparadetectarproblema",
        ]
    )
    text = (
        "TERMO DE DECLARACOES EM AUTO DE PRISAO EM FLAGRANTE QUE PRESTA A "
        "VITIMA: ANA SOUZA\nINQUERITO 9\n"
        f"{glued}\nNada mais declarou. Pag. 1 de 1"
    )

    result = build_structured_transcription([_chunk(5, 0, text)])

    assert result.status == "revisao_necessaria"
    testimony = result.testimonies[0]
    assert testimony["cobertura"] == "integral"
    assert testimony["paginas"][0]["palavras_coladas"] is True
    assert testimony["revisao_necessaria"] is True
    assert glued in testimony["texto_consolidado"]


def test_recognizes_declaration_heading_split_by_ocr_line_break() -> None:
    text = (
        "POLICIA CIVIL\nTERMO DE\nDECLARACOES EM AUTO DE PRISAO EM FLAGRANTE "
        "QUE PRESTA A VITIMA: ANA SOUZA\nINQUERITO 9\n"
        "A declarante confirmou os fatos. Nada mais declarou. Pag. 1 de 1"
    )

    result = build_structured_transcription([_chunk(5, 0, text)])

    assert len(result.testimonies) == 1
    assert result.testimonies[0]["tipo_documento"] == "declaracoes_vitima"
    assert result.testimonies[0]["pessoa"] == "ANA SOUZA"


def test_does_not_claim_integral_coverage_without_formal_ending() -> None:
    text = (
        "TERMO DE INTERROGATORIO DO INFRATOR: JOAO PEREIRA\n"
        "INQUERITO 44\nO interrogado apresentou sua versao. Pag. 1 de 1"
    )

    result = build_structured_transcription([_chunk(18, 0, text)])

    testimony = result.testimonies[0]
    assert testimony["papel"] == "reu"
    assert testimony["cobertura"] == "parcial"
    assert testimony["revisao_necessaria"] is True
    assert any("encerramento" in warning for warning in testimony["avisos"])


def test_returns_explicit_status_when_no_testimony_is_found() -> None:
    result = build_structured_transcription(
        [_chunk(1, 0, "Peticao inicial sem termo de oitiva.", "alta")]
    )

    assert result.status == "sem_depoimentos"
    assert result.testimonies == []
    assert "Nenhum termo" in result.warnings[0]


def test_ignores_narrative_reference_to_previous_testimony() -> None:
    text = (
        "Promotoria de Justica\nA vitima, em termo de depoimento, declarou que "
        "compareceu a delegacia durante o inquerito."
    )

    result = build_structured_transcription([_chunk(54, 0, text, "alta")])

    assert result.status == "sem_depoimentos"


def test_extracts_interrogated_person_with_gender_marker() -> None:
    text = (
        "POLICIA CIVIL\nTERMO DE INTERROGATORIO EM AUTO DE PRISAO EM FLAGRANTE\n"
        "INQUERITO 8\nO INFRATOR（A) FRANCISCO SUDERVAN ANDRADE, nacionalidade "
        "brasileira, foi ouvido. Nada mais disse. Pag. 1 de 1"
    )

    result = build_structured_transcription([_chunk(18, 0, text)])

    assert result.testimonies[0]["pessoa"] == "FRANCISCO SUDERVAN ANDRADE"
