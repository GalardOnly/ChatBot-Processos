from __future__ import annotations

from preparador_audiencia.embeddings import embedding_provider_from_spec
from preparador_audiencia.ensemble import (
    EnsembleIndexProgressCallback,
    index_process_chunks_ensemble,
    is_ensemble_spec,
    parse_ensemble_spec,
    search_process_ensemble,
)
from preparador_audiencia.lexical_search import (
    needs_lexical_priority,
    search_process_lexical,
)
from preparador_audiencia.repositories import ChunkRepository
from preparador_audiencia.search import SearchResult, index_process_chunks, search_process
from preparador_audiencia.settings import embedding_provider_from_environment
from preparador_audiencia.vector_store import ChromaVectorStore, safe_collection_name

ROUTED_QUERY_WEIGHT = 0.35
LEXICAL_QUERY_WEIGHT = 1.0
RECIPROCAL_RANK_OFFSET = 60


def index_process_chunks_configured(
    processo_id: str,
    chunks: ChunkRepository,
    embedding_spec: str | None = None,
    progress_callback: EnsembleIndexProgressCallback | None = None,
) -> int:
    spec = embedding_spec or embedding_provider_from_environment()
    if is_ensemble_spec(spec):
        if progress_callback is not None:
            return index_process_chunks_ensemble(
                processo_id,
                chunks,
                parse_ensemble_spec(spec),
                progress_callback=progress_callback,
            )
        return index_process_chunks_ensemble(processo_id, chunks, parse_ensemble_spec(spec))

    provider = embedding_provider_from_spec(spec)
    if progress_callback is not None:
        return index_process_chunks(
            processo_id=processo_id,
            chunks=chunks,
            embedding_provider=provider,
            vector_store=_vector_store_for_single_spec(spec),
            progress_callback=lambda current, total: progress_callback(
                spec,
                1,
                1,
                current,
                total,
            ),
        )
    return index_process_chunks(
        processo_id=processo_id,
        chunks=chunks,
        embedding_provider=provider,
        vector_store=_vector_store_for_single_spec(spec),
    )


def search_process_configured(
    processo_id: str,
    pergunta: str,
    top_k: int = 5,
    embedding_spec: str | None = None,
) -> list[SearchResult]:
    spec = embedding_spec or embedding_provider_from_environment()
    if is_ensemble_spec(spec):
        return search_process_ensemble(
            processo_id=processo_id,
            pergunta=pergunta,
            top_k=top_k,
            model_specs=parse_ensemble_spec(spec),
        )

    provider = embedding_provider_from_spec(spec)
    return search_process(
        processo_id=processo_id,
        pergunta=pergunta,
        top_k=top_k,
        embedding_provider=provider,
        vector_store=_vector_store_for_single_spec(spec),
    )


def search_process_queries_configured(
    processo_id: str,
    queries: list[tuple[str, float]],
    top_k: int = 5,
    embedding_spec: str | None = None,
) -> list[SearchResult]:
    resolved_queries = _unique_weighted_queries(queries)
    if not resolved_queries:
        return []
    if len(resolved_queries) == 1:
        return _search_process_hybrid_configured(
            processo_id=processo_id,
            pergunta=resolved_queries[0][0],
            top_k=top_k,
            embedding_spec=embedding_spec,
        )

    candidate_limit = max(top_k * 2, top_k)
    combined: dict[tuple[int, int], tuple[SearchResult, float]] = {}
    routed_priority_result: SearchResult | None = None
    maximum_score = sum(
        weight / (RECIPROCAL_RANK_OFFSET + 1)
        for _, weight in resolved_queries
    )
    for query_index, (query, weight) in enumerate(resolved_queries):
        results = _search_process_hybrid_configured(
            processo_id=processo_id,
            pergunta=query,
            top_k=candidate_limit,
            embedding_spec=embedding_spec,
        )
        if query_index > 0 and results and needs_lexical_priority(query):
            routed_priority_result = results[0]
        for rank, result in enumerate(results, start=1):
            key = (result.page_number, result.chunk_index)
            current_result, current_score = combined.get(key, (result, 0.0))
            rank_score = weight / (RECIPROCAL_RANK_OFFSET + rank)
            combined[key] = (current_result, current_score + rank_score)

    ranked = sorted(combined.values(), key=lambda item: item[1], reverse=True)
    fused = [
        SearchResult(
            text=result.text,
            page_number=result.page_number,
            chunk_index=result.chunk_index,
            document_type=result.document_type,
            score=round(score / maximum_score, 4),
            source_confidence=result.source_confidence,
        )
        for result, score in ranked[:top_k]
    ]
    if routed_priority_result is not None:
        return _include_result(fused, routed_priority_result, top_k)
    return fused


def search_process_queries_lexical(
    processo_id: str,
    queries: list[tuple[str, float]],
    top_k: int = 5,
) -> list[SearchResult]:
    resolved_queries = _unique_weighted_queries(queries)
    if not resolved_queries:
        return []
    candidate_limit = max(top_k * 2, top_k)
    weighted_results = [
        (
            search_process_lexical(
                processo_id=processo_id,
                pergunta=query,
                top_k=candidate_limit,
            ),
            weight,
        )
        for query, weight in resolved_queries
    ]
    return _fuse_ranked_results(weighted_results, top_k)


def _search_process_hybrid_configured(
    processo_id: str,
    pergunta: str,
    top_k: int,
    embedding_spec: str | None,
) -> list[SearchResult]:
    candidate_limit = max(top_k * 2, top_k)
    semantic = search_process_configured(
        processo_id=processo_id,
        pergunta=pergunta,
        top_k=candidate_limit,
        embedding_spec=embedding_spec,
    )
    lexical = search_process_lexical(
        processo_id=processo_id,
        pergunta=pergunta,
        top_k=candidate_limit,
    )
    if not lexical:
        return semantic[:top_k]
    if not semantic:
        return lexical[:top_k]
    fused = _fuse_ranked_results(
        [(semantic, 1.0), (lexical, LEXICAL_QUERY_WEIGHT)],
        top_k,
    )
    if needs_lexical_priority(pergunta):
        return _prioritize_result(fused, lexical[0], top_k)
    return fused


def _fuse_ranked_results(
    weighted_results: list[tuple[list[SearchResult], float]],
    top_k: int,
) -> list[SearchResult]:
    combined: dict[tuple[int, int], tuple[SearchResult, float]] = {}
    maximum_score = sum(
        weight / (RECIPROCAL_RANK_OFFSET + 1)
        for results, weight in weighted_results
        if results
    )
    for results, weight in weighted_results:
        for rank, result in enumerate(results, start=1):
            key = (result.page_number, result.chunk_index)
            current_result, current_score = combined.get(key, (result, 0.0))
            rank_score = weight / (RECIPROCAL_RANK_OFFSET + rank)
            combined[key] = (current_result, current_score + rank_score)
    if not combined or maximum_score <= 0:
        return []
    ranked = sorted(combined.values(), key=lambda item: item[1], reverse=True)
    return [
        SearchResult(
            text=result.text,
            page_number=result.page_number,
            chunk_index=result.chunk_index,
            document_type=result.document_type,
            score=round(score / maximum_score, 4),
            source_confidence=result.source_confidence,
        )
        for result, score in ranked[:top_k]
    ]


def _unique_weighted_queries(
    queries: list[tuple[str, float]],
) -> list[tuple[str, float]]:
    unique: dict[str, float] = {}
    for query, weight in queries:
        normalized = query.strip()
        if normalized and weight > 0:
            unique[normalized] = max(weight, unique.get(normalized, 0.0))
    return list(unique.items())


def _prioritize_result(
    results: list[SearchResult],
    preferred: SearchResult,
    top_k: int,
) -> list[SearchResult]:
    preferred_key = (preferred.page_number, preferred.chunk_index)
    remaining = [
        result
        for result in results
        if (result.page_number, result.chunk_index) != preferred_key
    ]
    return [preferred, *remaining][:top_k]


def _include_result(
    results: list[SearchResult],
    required: SearchResult,
    top_k: int,
) -> list[SearchResult]:
    required_key = (required.page_number, required.chunk_index)
    if any(
        (result.page_number, result.chunk_index) == required_key
        for result in results
    ):
        return results[:top_k]
    return [*results[: max(0, top_k - 1)], required]


def _vector_store_for_single_spec(spec: str) -> ChromaVectorStore:
    if spec.strip().lower() == "hash":
        return ChromaVectorStore()
    return ChromaVectorStore(collection_name=safe_collection_name("processo_chunks", spec))
