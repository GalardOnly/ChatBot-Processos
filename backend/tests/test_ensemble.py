from preparador_audiencia.ensemble import (
    is_ensemble_spec,
    parse_ensemble_spec,
    search_process_ensemble,
)
from preparador_audiencia.search import SearchResult


def test_parse_legal_ensemble_spec() -> None:
    assert parse_ensemble_spec("legal-ensemble") == ["jurisbert", "legal-bertimbau"]
    assert parse_ensemble_spec("ensemble:hash+bertikal") == ["hash", "bertikal"]
    assert is_ensemble_spec("legal-ensemble") is True
    assert is_ensemble_spec("hash") is False


def test_search_process_ensemble_combines_votes(monkeypatch) -> None:
    calls = []

    def fake_embedding_provider_from_spec(spec: str) -> object:
        return object()

    def fake_search_process(
        processo_id: str,
        pergunta: str,
        top_k: int,
        embedding_provider: object,
        vector_store: object,
    ) -> list[SearchResult]:
        calls.append((processo_id, pergunta, top_k, embedding_provider, vector_store))
        if len(calls) == 1:
            return [
                SearchResult("Trecho audiencia", 2, 0, "audiencia", 0.9),
                SearchResult("Outro trecho", 1, 0, None, 0.8),
            ]
        return [SearchResult("Trecho audiencia", 2, 0, "audiencia", 0.7)]

    monkeypatch.setattr(
        "preparador_audiencia.ensemble.embedding_provider_from_spec",
        fake_embedding_provider_from_spec,
    )
    monkeypatch.setattr(
        "preparador_audiencia.ensemble.ChromaVectorStore",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr("preparador_audiencia.ensemble.search_process", fake_search_process)

    results = search_process_ensemble(
        processo_id="proc_123",
        pergunta="qual audiencia?",
        top_k=1,
        model_specs=["modelo-a", "modelo-b"],
    )

    assert results[0].page_number == 2
    assert results[0].chunk_index == 0
    assert len(calls) == 2
