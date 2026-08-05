from urllib.parse import urlparse

from preparador_audiencia.legal_catalog import (
    PROCEDURAL_NULLITY_TOPIC_IDS,
    load_legal_topic,
)


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


def test_procedural_nullity_catalogs_use_official_versioned_sources() -> None:
    for topic_id in PROCEDURAL_NULLITY_TOPIC_IDS:
        topic = load_legal_topic(topic_id)
        source_ids = {source.id for source in topic.sources}

        assert topic.id == topic_id
        assert topic.version == "2026.08.04"
        assert topic.verified_at == "2026-08-04"
        assert len(topic.search_queries) >= 5
        assert topic.evidence_terms
        assert all(set(item.legal_source_ids) <= source_ids for item in topic.requirements)
        assert all(urlparse(source.url).scheme == "https" for source in topic.sources)
        assert all(
            urlparse(source.url).hostname.endswith(
                ("cnj.jus.br", "planalto.gov.br", "stf.jus.br", "stj.jus.br")
            )
            for source in topic.sources
        )


def test_only_total_absence_of_defense_is_decisive_without_prejudice() -> None:
    decisive = [
        (topic_id, requirement.id)
        for topic_id in PROCEDURAL_NULLITY_TOPIC_IDS
        for requirement in load_legal_topic(topic_id).requirements
        if requirement.decisive_without_prejudice
    ]

    assert decisive == [("ausencia_deficiencia_defesa", "defesa_tecnica_presente")]
