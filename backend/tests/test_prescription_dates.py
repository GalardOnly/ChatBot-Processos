from preparador_audiencia.prescription_dates import extract_prescription_data
from preparador_audiencia.repositories import ChunkRecord


def _chunk(text: str, *, page: int = 1, confidence: str = "alta") -> ChunkRecord:
    return ChunkRecord(
        id=1,
        processo_id="proc-1",
        page_number=page,
        chunk_index=0,
        text=text,
        document_type=None,
        source_confidence=confidence,
        vector_id=None,
        created_at="2026-08-03T00:00:00+00:00",
    )


def test_extracts_accented_essential_dates_and_source_page() -> None:
    result = extract_prescription_data(
        [
            _chunk(
                "O fato ocorreu em 10/02/2020. A denúncia foi recebida em 15/03/2020. "
                "O réu, nascido em 2 de abril de 1999, foi qualificado nos autos.",
                page=7,
            )
        ]
    )

    by_type = {item.event_type: item for item in result.dates}
    assert by_type["data_fato"].value.isoformat() == "2020-02-10"
    assert by_type["recebimento_denuncia"].value.isoformat() == "2020-03-15"
    assert by_type["nascimento_reu"].value.isoformat() == "1999-04-02"
    assert by_type["recebimento_denuncia"].page_number == 7
    assert by_type["recebimento_denuncia"].review_required is True


def test_extracts_article_and_penalty_as_candidate_only() -> None:
    result = extract_prescription_data(
        [_chunk("Art. 157. Pena - reclusão, de 4 (quatro) a 10 (dez) anos.", page=12)]
    )

    assert result.offenses[0].article == "Art. 157"
    assert result.offenses[0].maximum_penalty_months == 120
    assert result.offenses[0].review_required is True


def test_invalid_date_is_not_returned() -> None:
    result = extract_prescription_data([_chunk("O fato ocorreu em 31/02/2020.")])

    assert result.dates == []


def test_low_ocr_confidence_is_exposed() -> None:
    result = extract_prescription_data(
        [_chunk("A denúncia foi recebida em 15/03/2020.", confidence="baixa")]
    )

    assert result.dates[0].confidence == "baixa"
    assert any("OCR" in warning for warning in result.warnings)


def test_repeated_date_on_multiple_pages_is_consolidated() -> None:
    result = extract_prescription_data(
        [
            _chunk("O reu, nascido em 02/01/1990, foi qualificado.", page=2),
            _chunk("Consta que o acusado, nascido em 02/01/1990, foi citado.", page=20),
        ]
    )

    births = [item for item in result.dates if item.event_type == "nascimento_reu"]
    assert len(births) == 1
    assert births[0].page_number == 2


def test_repeated_article_prefers_occurrence_with_maximum_penalty() -> None:
    result = extract_prescription_data(
        [
            _chunk("Imputa-se o art. 155 ao acusado.", page=3),
            _chunk(
                "Art. 155. Pena - reclusao, de 1 (um) a 4 (quatro) anos.",
                page=9,
            ),
        ]
    )

    assert len(result.offenses) == 1
    assert result.offenses[0].maximum_penalty_months == 48
    assert result.offenses[0].page_number == 9
