from __future__ import annotations

from preparador_audiencia.embeddings import embedding_provider_from_spec
from preparador_audiencia.ensemble import (
    index_process_chunks_ensemble,
    is_ensemble_spec,
    parse_ensemble_spec,
    search_process_ensemble,
)
from preparador_audiencia.repositories import ChunkRepository
from preparador_audiencia.search import SearchResult, index_process_chunks, search_process
from preparador_audiencia.settings import embedding_provider_from_environment
from preparador_audiencia.vector_store import ChromaVectorStore, safe_collection_name


def index_process_chunks_configured(
    processo_id: str,
    chunks: ChunkRepository,
    embedding_spec: str | None = None,
) -> int:
    spec = embedding_spec or embedding_provider_from_environment()
    if is_ensemble_spec(spec):
        return index_process_chunks_ensemble(processo_id, chunks, parse_ensemble_spec(spec))

    provider = embedding_provider_from_spec(spec)
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


def _vector_store_for_single_spec(spec: str) -> ChromaVectorStore:
    if spec.strip().lower() == "hash":
        return ChromaVectorStore()
    return ChromaVectorStore(collection_name=safe_collection_name("processo_chunks", spec))
