from preparador_audiencia.testimony_body import extract_testimony_body


def test_extracts_literal_body_across_pages_and_excludes_formal_closing() -> None:
    pages = [
        (
            10,
            "TERMO DE DEPOIMENTO\nMARIA, brasileira. DISSE QUE viu o veiculo "
            "vermelho e anotou a placa.",
        ),
        (
            11,
            "A testemunha afirmou que eram 22h. Nada mais disse nem lhe foi "
            "perguntado. Assinaturas.",
        ),
    ]

    result = extract_testimony_body(pages)

    assert result.status == "segmentada"
    assert result.confidence == "alta"
    assert result.review_required is False
    assert result.start_page == 10
    assert result.end_page == 11
    assert result.start_marker == "DISSE QUE"
    assert result.end_marker == "Nada mais disse"
    assert [segment.page_number for segment in result.segments] == [10, 11]
    assert result.segments[0].text == (
        "DISSE QUE viu o veiculo vermelho e anotou a placa."
    )
    assert result.segments[1].text == "A testemunha afirmou que eram 22h."
    assert "Assinaturas" not in result.text


def test_preserves_accents_and_punctuation_from_extracted_text() -> None:
    pages = [
        (4, "Cabeçalho\nDECLAROU QUE não conhecia José; porém, viu-o às 18h. Nada mais declarou."),
    ]

    result = extract_testimony_body(pages)

    assert result.text == "DECLAROU QUE não conhecia José; porém, viu-o às 18h."


def test_marks_body_for_review_when_formal_closing_is_missing() -> None:
    result = extract_testimony_body([(3, "QUALIFICACAO\nRESPONDEU QUE estava em casa.")])

    assert result.status == "revisao_necessaria"
    assert result.confidence == "media"
    assert result.review_required is True
    assert result.text == "RESPONDEU QUE estava em casa."
    assert result.end_marker is None


def test_does_not_use_entire_document_when_start_marker_is_missing() -> None:
    result = extract_testimony_body(
        [(8, "TERMO DE DEPOIMENTO\nJOAO, brasileiro. Nada mais disse. Assinaturas.")]
    )

    assert result.status == "nao_localizada"
    assert result.text == ""
    assert result.segments == []
    assert result.review_required is True


def test_accepts_standalone_que_but_ignores_que_presta_in_heading() -> None:
    result = extract_testimony_body(
        [
            (
                9,
                "TERMO DE DEPOIMENTO QUE PRESTA A TESTEMUNHA: ANA\n"
                "QUE chegou ao local depois do fato; QUE nao viu o autor. "
                "Nada mais disse.",
            )
        ]
    )

    assert result.start_marker == "QUE"
    assert result.text.startswith("QUE chegou ao local")
