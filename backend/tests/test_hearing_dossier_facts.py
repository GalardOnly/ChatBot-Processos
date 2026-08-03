from preparador_audiencia.hearing_dossier_facts import detect_key_events
from preparador_audiencia.search import SearchResult


def _source(text: str, page: int) -> SearchResult:
    return SearchResult(text, page, 0, None, 1.0, "alta")


def test_detects_fixed_events_without_asking_the_llm() -> None:
    sources = [
        _source(
            "Denunciado nascido aos 05/11/1995. I - DOS FATOS Consta do incluso "
            "inquerito policial que no dia 02 de setembro de 2024, \u00e0s 12h, na Rua "
            "Joaquim Domingos Neto, n. 73, Apto. 201, Centro, desta Urbe, FRANCISCO "
            "foi preso em flagrante delito.",
            53,
        ),
        _source(
            "DISPOSITIVO RECEBO A DENUNCIA contra o reu. Documento liberado nos "
            "autos em 22/10/2024 as 11:19.",
            58,
        ),
        _source(
            "Foi concedida a liberdade provisoria. Periodo do Cumprimento da Medida "
            "Inicio: 03/09/2024 - Fim: 03/09/2025.",
            55,
        ),
    ]

    events = detect_key_events(sources)
    values = {(event.event_type, event.value, event.source.page_number) for event in events}

    assert ("nascimento_reu", "05/11/1995", 53) in values
    assert ("recebimento_denuncia", "22/10/2024", 58) in values
    assert ("prisao", "02 de setembro de 2024, \u00e0s 12h", 53) in values
    assert ("liberdade", "concedida a liberdade provisoria", 55) in values
    assert ("liberdade", "Inicio: 03/09/2024 - Fim: 03/09/2025", 55) in values
    assert any(event.event_type == "data_fato" for event in events)


def test_does_not_treat_caution_period_as_process_suspension() -> None:
    events = detect_key_events(
        [
            _source(
                "Medidas cautelares. Periodo do Cumprimento da Medida Inicio: "
                "03/09/2024 - Fim: 03/09/2025.",
                44,
            )
        ]
    )

    assert not any(event.event_type.startswith("suspensao") for event in events)
