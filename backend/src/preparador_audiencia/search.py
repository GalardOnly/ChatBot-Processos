from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from preparador_audiencia.embeddings import EmbeddingProvider, get_embedding_provider
from preparador_audiencia.repositories import ChunkRepository
from preparador_audiencia.settings import embedding_batch_size_from_environment
from preparador_audiencia.vector_store import ChromaVectorStore, VectorSearchResult

IndexProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True)
class SearchResult:
    text: str
    page_number: int
    chunk_index: int
    document_type: str | None
    score: float


def index_process_chunks(
    processo_id: str,
    chunks: ChunkRepository,
    embedding_provider: EmbeddingProvider | None = None,
    vector_store: ChromaVectorStore | None = None,
    *,
    batch_size: int | None = None,
    progress_callback: IndexProgressCallback | None = None,
) -> int:
    chunk_records = chunks.list_for_processo(processo_id)
    provider = embedding_provider or get_embedding_provider()
    store = vector_store or ChromaVectorStore()

    resolved_batch_size = batch_size or embedding_batch_size_from_environment()
    embeddings: list[list[float]] = []
    total = len(chunk_records)
    for start in range(0, total, resolved_batch_size):
        batch = chunk_records[start : start + resolved_batch_size]
        embeddings.extend(provider.embed_texts([chunk.text for chunk in batch]))
        if progress_callback is not None:
            progress_callback(min(start + len(batch), total), total)
    vector_ids_by_chunk_id = store.replace_process_chunks(
        processo_id=processo_id,
        chunks=chunk_records,
        embeddings=embeddings,
    )
    chunks.update_vector_ids(vector_ids_by_chunk_id)
    return len(chunk_records)


def search_process(
    processo_id: str,
    pergunta: str,
    top_k: int = 5,
    embedding_provider: EmbeddingProvider | None = None,
    vector_store: ChromaVectorStore | None = None,
) -> list[SearchResult]:
    provider = embedding_provider or get_embedding_provider()
    store = vector_store or ChromaVectorStore()
    query_embedding = provider.embed_query(pergunta)
    hits = store.search(processo_id=processo_id, query_embedding=query_embedding, top_k=top_k)
    return [_result_from_hit(hit) for hit in hits]


def _result_from_hit(hit: VectorSearchResult) -> SearchResult:
    return SearchResult(
        text=hit.text,
        page_number=hit.page_number,
        chunk_index=hit.chunk_index,
        document_type=hit.document_type,
        score=hit.score,
    )
