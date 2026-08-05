from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from time import perf_counter

from preparador_audiencia.embeddings import (
    clear_embedding_provider_cache,
    embedding_provider_from_spec,
    resolve_embedding_device,
    resolve_embedding_spec,
)
from preparador_audiencia.ensemble import parse_ensemble_spec
from preparador_audiencia.llm import llm_client_from_spec
from preparador_audiencia.prompt_security import partition_adversarial_sources
from preparador_audiencia.question_router import route_question
from preparador_audiencia.retrieval import (
    ROUTED_QUERY_WEIGHT,
    search_process_queries_configured,
)
from preparador_audiencia.search import SearchResult
from preparador_audiencia.settings import (
    embedding_device_from_environment,
    embedding_provider_from_environment,
)


@dataclass(frozen=True)
class EmbeddingRuntimeTiming:
    dispositivo: str
    inicializacao_ms: int


@dataclass(frozen=True)
class EmbeddingLoadTiming:
    spec: str
    modelo: str | None
    rotulo: str
    dispositivo: str
    carregamento_ms: int
    primeiro_embedding_ms: int
    dimensoes: int


@dataclass(frozen=True)
class RetrievalTiming:
    execucao: int
    latencia_ms: int
    fontes_recuperadas: int


@dataclass(frozen=True)
class LLMCallTiming:
    modelo: str
    chamada_total_ms: int
    provedor_ms: int
    fontes_enviadas: int
    erro: str | None


@dataclass(frozen=True)
class LatencySummary:
    inicializacao_runtime_ms: int
    carga_modelos_ms: int
    primeiros_embeddings_ms: int
    carga_embeddings_ms: int
    primeira_recuperacao_ms: int
    recuperacao_quente_mediana_ms: int
    chamada_gemini_ms: int | None
    total_frio_estimado_ms: int | None
    total_quente_estimado_ms: int | None


@dataclass(frozen=True)
class ChatLatencyReport:
    processo_id: str
    pergunta: str
    embedding_spec: str
    top_k: int
    gerado_em: str
    runtime_embedding: EmbeddingRuntimeTiming
    modelos_embedding: tuple[EmbeddingLoadTiming, ...]
    recuperacoes: tuple[RetrievalTiming, ...]
    chamada_llm: LLMCallTiming | None
    resumo: LatencySummary


def profile_chat_latency(
    processo_id: str,
    pergunta: str,
    *,
    top_k: int = 5,
    repetitions: int = 3,
    embedding_spec: str | None = None,
    llm_model: str | None = None,
    max_llm_calls: int = 0,
) -> ChatLatencyReport:
    if top_k <= 0:
        raise ValueError("top_k deve ser maior que zero.")
    if repetitions <= 0:
        raise ValueError("repetitions deve ser maior que zero.")
    if llm_model is not None and max_llm_calls < 1:
        raise ValueError("A medicao da LLM exige max_llm_calls de pelo menos 1.")

    resolved_embedding_spec = embedding_spec or embedding_provider_from_environment()
    runtime_timing = profile_embedding_runtime(resolved_embedding_spec)
    embedding_timings = profile_embedding_loads(
        resolved_embedding_spec,
        pergunta,
    )
    question_route = route_question(pergunta)
    queries = [
        (pergunta, 1.0),
        (question_route.guide_query(), ROUTED_QUERY_WEIGHT),
    ]

    retrieval_timings: list[RetrievalTiming] = []
    sources: list[SearchResult] = []
    for run_number in range(1, repetitions + 1):
        started = perf_counter()
        sources = search_process_queries_configured(
            processo_id=processo_id,
            queries=queries,
            top_k=top_k,
            embedding_spec=resolved_embedding_spec,
        )
        retrieval_timings.append(
            RetrievalTiming(
                execucao=run_number,
                latencia_ms=_elapsed_ms(started),
                fontes_recuperadas=len(sources),
            )
        )

    llm_timing = None
    if llm_model is not None:
        reliable_sources = _reliable_sources(sources)
        if not reliable_sources:
            raise RuntimeError(
                "A recuperacao nao encontrou fonte segura para medir a chamada da LLM."
            )
        llm_started = perf_counter()
        answer = llm_client_from_spec(llm_model).answer(
            question_route.llm_question(),
            reliable_sources,
        )
        llm_timing = LLMCallTiming(
            modelo=answer.model,
            chamada_total_ms=_elapsed_ms(llm_started),
            provedor_ms=answer.latency_ms,
            fontes_enviadas=len(reliable_sources),
            erro=answer.error,
        )

    summary = _summarize_latency(
        runtime_timing,
        embedding_timings,
        retrieval_timings,
        llm_timing,
    )
    return ChatLatencyReport(
        processo_id=processo_id,
        pergunta=pergunta,
        embedding_spec=resolved_embedding_spec,
        top_k=top_k,
        gerado_em=datetime.now(UTC).isoformat(),
        runtime_embedding=runtime_timing,
        modelos_embedding=tuple(embedding_timings),
        recuperacoes=tuple(retrieval_timings),
        chamada_llm=llm_timing,
        resumo=summary,
    )


def profile_embedding_runtime(embedding_spec: str) -> EmbeddingRuntimeTiming:
    resolved_specs = [
        resolve_embedding_spec(spec) for spec in parse_ensemble_spec(embedding_spec)
    ]
    if all(spec.provider == "hash" for spec in resolved_specs):
        return EmbeddingRuntimeTiming(dispositivo="cpu", inicializacao_ms=0)

    started = perf_counter()
    import torch
    import transformers  # noqa: F401

    if any(spec.provider == "sentence_transformers" for spec in resolved_specs):
        import sentence_transformers  # noqa: F401

    device = resolve_embedding_device(torch, embedding_device_from_environment())
    if device.startswith("cuda"):
        torch.empty(1, device=device)
        torch.cuda.synchronize(device)
    return EmbeddingRuntimeTiming(
        dispositivo=device,
        inicializacao_ms=_elapsed_ms(started),
    )


def profile_embedding_loads(
    embedding_spec: str,
    sample_text: str,
) -> list[EmbeddingLoadTiming]:
    clear_embedding_provider_cache()
    timings = []
    for member_spec in parse_ensemble_spec(embedding_spec):
        resolved = resolve_embedding_spec(member_spec)
        load_started = perf_counter()
        provider = embedding_provider_from_spec(member_spec)
        load_ms = _elapsed_ms(load_started)

        embedding_started = perf_counter()
        vector = provider.embed_query(sample_text)
        embedding_ms = _elapsed_ms(embedding_started)
        timings.append(
            EmbeddingLoadTiming(
                spec=member_spec,
                modelo=resolved.model_name,
                rotulo=resolved.label,
                dispositivo=str(getattr(provider, "device", "cpu")),
                carregamento_ms=load_ms,
                primeiro_embedding_ms=embedding_ms,
                dimensoes=len(vector),
            )
        )
    return timings


def write_chat_latency_report(
    report: ChatLatencyReport,
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def _reliable_sources(sources: list[SearchResult]) -> list[SearchResult]:
    security_checked, _flagged = partition_adversarial_sources(sources)
    return [
        source
        for source in security_checked
        if source.source_confidence in {"alta", "media"}
    ]


def _summarize_latency(
    runtime_timing: EmbeddingRuntimeTiming,
    embedding_timings: list[EmbeddingLoadTiming],
    retrieval_timings: list[RetrievalTiming],
    llm_timing: LLMCallTiming | None,
) -> LatencySummary:
    model_load_total = sum(timing.carregamento_ms for timing in embedding_timings)
    first_embedding_total = sum(
        timing.primeiro_embedding_ms for timing in embedding_timings
    )
    embedding_total = (
        runtime_timing.inicializacao_ms + model_load_total + first_embedding_total
    )
    first_retrieval = retrieval_timings[0].latencia_ms
    warm_values = [timing.latencia_ms for timing in retrieval_timings[1:]]
    if not warm_values:
        warm_values = [first_retrieval]
    warm_retrieval = round(median(warm_values))
    llm_ms = llm_timing.chamada_total_ms if llm_timing is not None else None
    return LatencySummary(
        inicializacao_runtime_ms=runtime_timing.inicializacao_ms,
        carga_modelos_ms=model_load_total,
        primeiros_embeddings_ms=first_embedding_total,
        carga_embeddings_ms=embedding_total,
        primeira_recuperacao_ms=first_retrieval,
        recuperacao_quente_mediana_ms=warm_retrieval,
        chamada_gemini_ms=llm_ms,
        total_frio_estimado_ms=(
            embedding_total + first_retrieval + llm_ms
            if llm_ms is not None
            else None
        ),
        total_quente_estimado_ms=(
            warm_retrieval + llm_ms if llm_ms is not None else None
        ),
    )


def _elapsed_ms(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1000))
