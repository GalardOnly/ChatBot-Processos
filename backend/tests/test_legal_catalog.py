from urllib.parse import urlparse

from preparador_audiencia.legal_catalog import load_legal_topic


def test_recognition_catalog_uses_versioned_official_sources() -> None:
    topic = load_legal_topic("reconhecimento_pessoas")

    assert topic.version == "2026.08.02"
    assert topic.verified_at == "2026-08-02"
    assert len(topic.sources) == 4
    assert {source.id for source in topic.sources} == {
        "cpp_arts_226_228",
        "cnj_resolucao_484_2022",
        "stj_tema_1258",
        "stj_hc_598886_sc",
    }
    assert all(urlparse(source.url).scheme == "https" for source in topic.sources)
    assert all(
        urlparse(source.url).hostname.endswith(
            ("cnj.jus.br", "planalto.gov.br", "stj.jus.br")
        )
        for source in topic.sources
    )


def test_recognition_requirements_reference_known_legal_sources() -> None:
    topic = load_legal_topic("reconhecimento_pessoas")
    source_ids = {source.id for source in topic.sources}

    assert {item.category for item in topic.requirements} == {
        "aplicabilidade",
        "validade",
        "impacto",
    }
    assert len(topic.requirements) == len({item.id for item in topic.requirements})
    assert all(set(item.legal_source_ids) <= source_ids for item in topic.requirements)
    assert len(topic.search_queries) >= 5
