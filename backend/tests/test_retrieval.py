from preparador_audiencia.retrieval import (
    index_process_chunks_configured,
    search_process_configured,
)
from preparador_audiencia.search import SearchResult


def test_index_process_chunks_configured_uses_ensemble(monkeypatch) -> None:
    calls = []
    chunk_repository = object()

    def fake_index(processo_id, chunks, model_specs):
        calls.append((processo_id, chunks, model_specs))
        return 7

    monkeypatch.setattr("preparador_audiencia.retrieval.index_process_chunks_ensemble", fake_index)

    result = index_process_chunks_configured(
        processo_id="proc_123",
        chunks=chunk_repository,
        embedding_spec="legal-ensemble",
    )

    assert result == 7
    assert calls[0][0] == "proc_123"
    assert calls[0][1] is chunk_repository
    assert calls[0][2] == ["jurisbert", "legal-bertimbau"]


def test_search_process_configured_uses_ensemble(monkeypatch) -> None:
    calls = []
    expected = [SearchResult("Trecho", 1, 0, None, 0.9)]

    def fake_search(processo_id, pergunta, top_k, model_specs):
        calls.append((processo_id, pergunta, top_k, model_specs))
        return expected

    monkeypatch.setattr("preparador_audiencia.retrieval.search_process_ensemble", fake_search)

    result = search_process_configured(
        processo_id="proc_123",
        pergunta="qual audiencia?",
        top_k=3,
        embedding_spec="legal-ensemble",
    )

    assert result == expected
    assert calls == [
        (
            "proc_123",
            "qual audiencia?",
            3,
            ["jurisbert", "legal-bertimbau"],
        )
    ]
