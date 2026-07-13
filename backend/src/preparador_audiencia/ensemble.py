from __future__ import annotations

from dataclasses import dataclass, field

from preparador_audiencia.embeddings import embedding_provider_from_spec
from preparador_audiencia.repositories import ChunkRepository
from preparador_audiencia.search import SearchResult, index_process_chunks, search_process
from preparador_audiencia.vector_store import ChromaVectorStore, safe_collection_name

DEFAULT_LEGAL_ENSEMBLE_SPECS = ["bertikal", "jurisbert", "legal-bertimbau"]


@dataclass
class CombinedHit:
    text: str
    page_number: int
    chunk_index: int
    document_type: str | None
    score_sum: float = 0.0
    votes: int = 0
    best_score: float = 0.0
    models: list[str] = field(default_factory=list)

    def to_search_result(self, total_models: int) -> SearchResult:
        average_score = self.score_sum / max(1, self.votes)
        vote_score = self.votes / max(1, total_models)
        return SearchResult(
            text=self.text,
            page_number=self.page_number,
            chunk_index=self.chunk_index,
            document_type=self.document_type,
            score=round((0.65 * average_score) + (0.35 * vote_score), 4),
        )


def parse_ensemble_spec(spec: str) -> list[str]:
    normalized = spec.strip().lower()
    if normalized in {"legal-ensemble", "ensemble-legal", "juridico-ensemble"}:
        return DEFAULT_LEGAL_ENSEMBLE_SPECS
    if normalized.startswith("ensemble:"):
        members = [member.strip() for member in spec.removeprefix("ensemble:").split("+")]
        return [member for member in members if member]
    return [spec]


def is_ensemble_spec(spec: str) -> bool:
    return len(parse_ensemble_spec(spec)) > 1


def index_process_chunks_ensemble(
    processo_id: str,
    chunks: ChunkRepository,
    model_specs: list[str] | None = None,
) -> int:
    specs = model_specs or DEFAULT_LEGAL_ENSEMBLE_SPECS
    indexed = 0
    for spec in specs:
        provider = embedding_provider_from_spec(spec)
        store = ChromaVectorStore(collection_name=_collection_name_for_spec(spec))
        indexed = index_process_chunks(processo_id, chunks, provider, store)
    return indexed


def search_process_ensemble(
    processo_id: str,
    pergunta: str,
    top_k: int = 5,
    model_specs: list[str] | None = None,
    per_model_top_k: int | None = None,
) -> list[SearchResult]:
    specs = model_specs or DEFAULT_LEGAL_ENSEMBLE_SPECS
    per_model_limit = per_model_top_k or max(top_k * 2, 5)
    combined: dict[tuple[int, int], CombinedHit] = {}

    for spec in specs:
        provider = embedding_provider_from_spec(spec)
        store = ChromaVectorStore(collection_name=_collection_name_for_spec(spec))
        results = search_process(
            processo_id=processo_id,
            pergunta=pergunta,
            top_k=per_model_limit,
            embedding_provider=provider,
            vector_store=store,
        )
        _merge_model_results(combined, spec, results)

    ranked = sorted(
        combined.values(),
        key=lambda hit: (hit.votes, hit.score_sum, hit.best_score),
        reverse=True,
    )
    return [hit.to_search_result(total_models=len(specs)) for hit in ranked[:top_k]]


def _merge_model_results(
    combined: dict[tuple[int, int], CombinedHit],
    model_spec: str,
    results: list[SearchResult],
) -> None:
    for rank, result in enumerate(results, start=1):
        key = (result.page_number, result.chunk_index)
        rank_score = 1.0 / rank
        score = (0.5 * result.score) + (0.5 * rank_score)
        hit = combined.get(key)
        if hit is None:
            hit = CombinedHit(
                text=result.text,
                page_number=result.page_number,
                chunk_index=result.chunk_index,
                document_type=result.document_type,
            )
            combined[key] = hit
        hit.score_sum += score
        hit.votes += 1
        hit.best_score = max(hit.best_score, score)
        hit.models.append(model_spec)


def _collection_name_for_spec(spec: str) -> str:
    return safe_collection_name("processo_chunks", spec)
