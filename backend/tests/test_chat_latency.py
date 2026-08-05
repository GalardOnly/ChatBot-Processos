import json

import pytest

from preparador_audiencia.chat_latency import (
    EmbeddingLoadTiming,
    EmbeddingRuntimeTiming,
    profile_chat_latency,
    profile_embedding_loads,
    write_chat_latency_report,
)
from preparador_audiencia.llm import LLMAnswer
from preparador_audiencia.search import SearchResult


class FakeEmbeddingProvider:
    device = "cpu"

    def embed_query(self, _text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


class FakeLLMClient:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def answer(self, pergunta: str, sources: list[SearchResult]) -> LLMAnswer:
        self.calls.append(pergunta)
        return LLMAnswer(
            model="gemini:teste",
            answer="Resposta sustentada [p. 2].",
            latency_ms=40,
        )


def _source() -> SearchResult:
    return SearchResult(
        text="A decisao foi proferida na audiencia.",
        page_number=2,
        chunk_index=0,
        document_type="decisao",
        score=0.9,
        source_confidence="alta",
    )


def _embedding_timing() -> EmbeddingLoadTiming:
    return EmbeddingLoadTiming(
        spec="jurisbert",
        modelo="modelo-local",
        rotulo="JurisBERT",
        dispositivo="cpu",
        carregamento_ms=100,
        primeiro_embedding_ms=20,
        dimensoes=768,
    )


def _runtime_timing() -> EmbeddingRuntimeTiming:
    return EmbeddingRuntimeTiming(dispositivo="cpu", inicializacao_ms=30)


def test_profiles_embedding_load_and_first_inference(monkeypatch) -> None:
    cleared = []
    monkeypatch.setattr(
        "preparador_audiencia.chat_latency.clear_embedding_provider_cache",
        lambda: cleared.append(True),
    )
    monkeypatch.setattr(
        "preparador_audiencia.chat_latency.embedding_provider_from_spec",
        lambda _spec: FakeEmbeddingProvider(),
    )

    timings = profile_embedding_loads("hash", "Qual foi a decisao?")

    assert cleared == [True]
    assert len(timings) == 1
    assert timings[0].dimensoes == 3
    assert timings[0].dispositivo == "cpu"


def test_profiles_retrieval_without_external_call(monkeypatch) -> None:
    searches = []
    monkeypatch.setattr(
        "preparador_audiencia.chat_latency.profile_embedding_runtime",
        lambda *_args: _runtime_timing(),
    )
    monkeypatch.setattr(
        "preparador_audiencia.chat_latency.profile_embedding_loads",
        lambda *_args: [_embedding_timing()],
    )

    def fake_search(**kwargs):
        searches.append(kwargs["queries"])
        return [_source()]

    monkeypatch.setattr(
        "preparador_audiencia.chat_latency.search_process_queries_configured",
        fake_search,
    )
    monkeypatch.setattr(
        "preparador_audiencia.chat_latency.llm_client_from_spec",
        lambda _spec: pytest.fail("A LLM nao deveria ser chamada"),
    )

    report = profile_chat_latency(
        "proc_123",
        "Qual foi a decisao?",
        repetitions=3,
        embedding_spec="jurisbert",
    )

    assert len(searches) == 3
    assert report.chamada_llm is None
    assert report.resumo.inicializacao_runtime_ms == 30
    assert report.resumo.carga_modelos_ms == 100
    assert report.resumo.primeiros_embeddings_ms == 20
    assert report.resumo.carga_embeddings_ms == 150
    assert report.resumo.total_quente_estimado_ms is None


def test_profiles_exactly_one_gemini_call(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "preparador_audiencia.chat_latency.profile_embedding_runtime",
        lambda *_args: _runtime_timing(),
    )
    monkeypatch.setattr(
        "preparador_audiencia.chat_latency.profile_embedding_loads",
        lambda *_args: [_embedding_timing()],
    )
    monkeypatch.setattr(
        "preparador_audiencia.chat_latency.search_process_queries_configured",
        lambda **_kwargs: [_source()],
    )
    monkeypatch.setattr(
        "preparador_audiencia.chat_latency.llm_client_from_spec",
        lambda _spec: FakeLLMClient(calls),
    )

    report = profile_chat_latency(
        "proc_123",
        "Qual foi a decisao?",
        repetitions=2,
        embedding_spec="jurisbert",
        llm_model="gemini:teste",
        max_llm_calls=1,
    )

    assert len(calls) == 1
    assert report.chamada_llm is not None
    assert report.chamada_llm.modelo == "gemini:teste"
    assert report.chamada_llm.provedor_ms == 40
    assert report.resumo.total_frio_estimado_ms is not None


def test_rejects_llm_measurement_before_work_without_budget(monkeypatch) -> None:
    monkeypatch.setattr(
        "preparador_audiencia.chat_latency.profile_embedding_loads",
        lambda *_args: pytest.fail("Os modelos nao deveriam ser carregados"),
    )

    with pytest.raises(ValueError, match="max_llm_calls"):
        profile_chat_latency(
            "proc_123",
            "Qual foi a decisao?",
            llm_model="gemini:teste",
            max_llm_calls=0,
        )


def test_writes_json_report(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "preparador_audiencia.chat_latency.profile_embedding_runtime",
        lambda *_args: _runtime_timing(),
    )
    monkeypatch.setattr(
        "preparador_audiencia.chat_latency.profile_embedding_loads",
        lambda *_args: [_embedding_timing()],
    )
    monkeypatch.setattr(
        "preparador_audiencia.chat_latency.search_process_queries_configured",
        lambda **_kwargs: [_source()],
    )
    report = profile_chat_latency(
        "proc_123",
        "Qual foi a decisao?",
        repetitions=1,
        embedding_spec="jurisbert",
    )

    output = write_chat_latency_report(report, tmp_path / "latencia.json")
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["processo_id"] == "proc_123"
    assert payload["modelos_embedding"][0]["rotulo"] == "JurisBERT"
