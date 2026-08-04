from preparador_audiencia.judgment_structure import build_judgment_structure
from preparador_audiencia.repositories import ChunkRecord


def _chunk(page: int, text: str, *, index: int = 0) -> ChunkRecord:
    return ChunkRecord(
        id=page * 10 + index,
        processo_id="proc-1",
        page_number=page,
        chunk_index=index,
        text=text,
        document_type=None,
        source_confidence="alta",
        vector_id=None,
        created_at="2026-08-04T00:00:00+00:00",
    )


def _sentence_chunks() -> list[ChunkRecord]:
    return [
        _chunk(
            20,
            "S E N T E N C A\nRelatorio e fundamentacao. O acusado responde pelo fato.",
        ),
        _chunk(
            21,
            "Diante do exposto, JULGO PROCEDENTE a pretensao e CONDENO o reu nas "
            "sancoes do art. 155 do Codigo Penal. Pena-base em quatro anos de "
            "reclusao. Pena intermediaria em tres anos e seis meses de reclusao. "
            "Torno definitiva a pena em tres anos e seis meses de reclusao e 10 "
            "dias-multa. Fixo o regime inicial aberto. Substituo a pena privativa "
            "por duas penas restritivas de direitos.",
        ),
        _chunk(
            22,
            "CERTIDAO DE TRANSITO EM JULGADO\nCertifico que transitou em julgado "
            "para ambas as partes em 15/06/2025.",
        ),
    ]


def test_structures_sentence_penalty_and_final_judgment() -> None:
    result = build_judgment_structure(_sentence_chunks())

    assert result.status == "concluido"
    assert len(result.decisions) == 1
    decision = result.decisions[0]
    assert decision["resultado"] == "condenatoria"
    assert decision["pagina_inicial"] == 20
    assert decision["pagina_final"] == 21
    assert decision["dispositivo"]["paginas"] == [21]
    assert decision["artigos_aplicados"][0]["artigo"] == "art. 155"
    assert decision["artigos_aplicados"][0]["pagina"] == 21

    penalties = {item["fase"]: item for item in decision["penas_aplicadas"]}
    assert penalties["base"]["anos"] == 4
    assert penalties["intermediaria"]["anos"] == 3
    assert penalties["intermediaria"]["meses"] == 6
    assert penalties["definitiva"]["anos"] == 3
    assert penalties["definitiva"]["meses"] == 6
    assert decision["multa"]["dias_multa"] == 10
    assert decision["regime_inicial"]["valor"] == "aberto"
    assert decision["substituicao_pena"]["resultado"] == "deferida"

    assert result.final_judgments[0]["escopo"] == "ambas_partes"
    assert result.final_judgments[0]["data"] == "2025-06-15"
    assert result.final_judgments[0]["pagina"] == 22


def test_marks_mixed_decision_and_missing_definitive_penalty_for_review() -> None:
    result = build_judgment_structure(
        [
            _chunk(1, "SENTENCA"),
            _chunk(
                2,
                "Ante o exposto, condeno quanto ao primeiro fato e absolvo quanto "
                "ao segundo fato.",
            ),
        ]
    )

    decision = result.decisions[0]
    assert result.status == "revisao_necessaria"
    assert decision["resultado"] == "mista"
    assert decision["revisao_necessaria"] is True
    assert any("pena definitiva" in warning for warning in decision["avisos"])


def test_returns_not_found_without_decision_heading() -> None:
    result = build_judgment_structure([_chunk(1, "Peticao da defesa sem decisao.")])

    assert result.status == "nao_localizada"
    assert result.decisions == []


def test_understands_numeric_penalty_and_defense_only_final_judgment() -> None:
    result = build_judgment_structure(
        [
            _chunk(4, "SENTENCA"),
            _chunk(
                5,
                "Diante do exposto, condeno o acusado. Pena definitiva em 2 (dois) "
                "anos, 3 (tres) meses e 5 (cinco) dias de detencao.",
            ),
            _chunk(
                8,
                "Certifico o transito em julgado para a defesa em 3 de maio de 2026.",
            ),
        ]
    )

    penalty = result.decisions[0]["penas_aplicadas"][0]
    assert (penalty["anos"], penalty["meses"], penalty["dias"]) == (2, 3, 5)
    assert penalty["especie"] == "detencao"
    assert result.final_judgments[0]["escopo"] == "defesa"
    assert result.final_judgments[0]["data"] == "2026-05-03"
