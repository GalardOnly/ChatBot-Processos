from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean

from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.embeddings import embedding_provider_from_spec
from preparador_audiencia.ensemble import (
    index_process_chunks_ensemble,
    is_ensemble_spec,
    parse_ensemble_spec,
    search_process_ensemble,
)
from preparador_audiencia.llm import LLMAnswer, LLMClient, llm_client_from_spec
from preparador_audiencia.repositories import ChunkRepository
from preparador_audiencia.search import SearchResult, index_process_chunks, search_process
from preparador_audiencia.vector_store import ChromaVectorStore, safe_collection_name


@dataclass(frozen=True)
class EvaluationCase:
    id: str
    pergunta: str
    expected_pages: list[int]
    expected_terms: list[str]


@dataclass(frozen=True)
class RetrievalCaseResult:
    case_id: str
    pergunta: str
    top_pages: list[int]
    expected_pages: list[int]
    expected_terms: list[str]
    hit: bool
    reciprocal_rank: float
    score: float
    sources: list[SearchResult]


@dataclass(frozen=True)
class EmbeddingEvaluationResult:
    model_spec: str
    indexed_chunks: int
    average_score: float
    average_reciprocal_rank: float
    hit_rate: float
    cases: list[RetrievalCaseResult]


@dataclass(frozen=True)
class LLMEvaluationResult:
    model: str
    case_id: str
    pergunta: str
    score: float
    answer: str
    latency_ms: int
    error: str | None


@dataclass(frozen=True)
class POCModelEvaluationReport:
    processo_id: str
    top_k: int
    best_embedding_model: str | None
    best_llm_model: str | None
    embedding_results: list[EmbeddingEvaluationResult]
    llm_results: list[LLMEvaluationResult]

    def to_dict(self) -> dict:
        return asdict(self)


def load_evaluation_cases(path: str | Path) -> list[EvaluationCase]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    cases_payload = payload["cases"] if isinstance(payload, dict) else payload
    return [
        EvaluationCase(
            id=str(item["id"]),
            pergunta=str(item["pergunta"]),
            expected_pages=[int(page) for page in item.get("expected_pages", [])],
            expected_terms=[str(term) for term in item.get("expected_terms", [])],
        )
        for item in cases_payload
    ]


def run_poc_model_evaluation(
    processo_id: str,
    cases: list[EvaluationCase],
    embedding_specs: list[str],
    llm_models: list[str],
    top_k: int = 5,
) -> POCModelEvaluationReport:
    connection = connect_database()
    initialize_database(connection)
    chunk_repository = ChunkRepository(connection)

    embedding_results = [
        evaluate_embedding_model(processo_id, chunk_repository, cases, spec, top_k)
        for spec in embedding_specs
    ]
    best_embedding = _best_embedding_result(embedding_results)
    llm_results: list[LLMEvaluationResult] = []

    if best_embedding is not None and llm_models and _can_run_any_llm(llm_models):
        llm_results = evaluate_llm_models(llm_models, best_embedding.cases)

    best_llm_model = _best_llm_model(llm_results)
    return POCModelEvaluationReport(
        processo_id=processo_id,
        top_k=top_k,
        best_embedding_model=best_embedding.model_spec if best_embedding else None,
        best_llm_model=best_llm_model,
        embedding_results=embedding_results,
        llm_results=llm_results,
    )


def evaluate_embedding_model(
    processo_id: str,
    chunks: ChunkRepository,
    cases: list[EvaluationCase],
    model_spec: str,
    top_k: int,
) -> EmbeddingEvaluationResult:
    if is_ensemble_spec(model_spec):
        specs = parse_ensemble_spec(model_spec)
        indexed = index_process_chunks_ensemble(processo_id, chunks, specs)
        case_results = [
            evaluate_retrieval_case(
                case=case,
                sources=search_process_ensemble(processo_id, case.pergunta, top_k, specs),
            )
            for case in cases
        ]
        return _embedding_result(model_spec, indexed, case_results)

    provider = embedding_provider_from_spec(model_spec)
    store = ChromaVectorStore(collection_name=safe_collection_name("poc_eval", model_spec))
    indexed = index_process_chunks(processo_id, chunks, provider, store)
    case_results = [
        evaluate_retrieval_case(
            case=case,
            sources=search_process(processo_id, case.pergunta, top_k, provider, store),
        )
        for case in cases
    ]
    return _embedding_result(model_spec, indexed, case_results)


def evaluate_retrieval_case(
    case: EvaluationCase,
    sources: list[SearchResult],
) -> RetrievalCaseResult:
    top_pages = [source.page_number for source in sources]
    reciprocal_rank = _reciprocal_rank(top_pages, case.expected_pages)
    hit = reciprocal_rank > 0
    term_score = _term_score(" ".join(source.text for source in sources), case.expected_terms)
    page_score = 1.0 if hit else 0.0
    score = (0.7 * page_score) + (0.3 * term_score)
    return RetrievalCaseResult(
        case_id=case.id,
        pergunta=case.pergunta,
        top_pages=top_pages,
        expected_pages=case.expected_pages,
        expected_terms=case.expected_terms,
        hit=hit,
        reciprocal_rank=reciprocal_rank,
        score=round(score, 4),
        sources=sources,
    )


def evaluate_llm_models(
    models: list[str],
    retrieval_cases: list[RetrievalCaseResult],
    clients: dict[str, LLMClient] | None = None,
) -> list[LLMEvaluationResult]:
    results: list[LLMEvaluationResult] = []
    for model in models:
        try:
            client = clients[model] if clients and model in clients else llm_client_from_spec(model)
        except Exception as exc:
            results.extend(_failed_llm_results(model, retrieval_cases, str(exc)))
            continue
        for case in retrieval_cases:
            answer = client.answer(case.pergunta, case.sources)
            results.append(
                LLMEvaluationResult(
                    model=answer.model,
                    case_id=case.case_id,
                    pergunta=case.pergunta,
                    score=score_llm_answer(answer, case),
                    answer=answer.answer,
                    latency_ms=answer.latency_ms,
                    error=answer.error,
                )
            )
    return results


def score_llm_answer(answer: LLMAnswer, case: RetrievalCaseResult) -> float:
    if answer.error or not answer.answer.strip():
        return 0.0
    citation_score = _citation_score(answer.answer, case.expected_pages)
    term_score = _term_score(answer.answer, case.expected_terms)
    return round((0.55 * citation_score) + (0.45 * term_score), 4)


def write_report_files(report: POCModelEvaluationReport, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    path.with_suffix(".md").write_text(render_markdown_report(report), encoding="utf-8")


def render_markdown_report(report: POCModelEvaluationReport) -> str:
    lines = [
        "# Relatorio da PoC de Modelos",
        "",
        f"- Processo: `{report.processo_id}`",
        f"- Top K: `{report.top_k}`",
        f"- Melhor recuperador: `{report.best_embedding_model or 'nao definido'}`",
        f"- Melhor LLM: `{report.best_llm_model or 'nao avaliado'}`",
        "",
        "## Recuperacao",
        "",
        "| Modelo | Score medio | Hit rate | MRR |",
        "|---|---:|---:|---:|",
    ]
    for result in report.embedding_results:
        lines.append(
            f"| `{result.model_spec}` | {result.average_score:.4f} | "
            f"{result.hit_rate:.4f} | {result.average_reciprocal_rank:.4f} |"
        )

    if report.llm_results:
        lines.extend(
            [
                "",
                "## LLMs",
                "",
                "| Modelo | Caso | Score | Latencia | Erro |",
                "|---|---|---:|---:|---|",
            ]
        )
        for result in report.llm_results:
            lines.append(
                f"| `{result.model}` | `{result.case_id}` | {result.score:.4f} | "
                f"{result.latency_ms} ms | {result.error or ''} |"
            )
    else:
        lines.extend(
            [
                "",
                "## LLMs",
                "",
                "Avaliacao de LLM nao executada. Defina `GEMINI_API_KEY` "
                "ou `GROQ_API_KEY`.",
            ]
        )
    return "\n".join(lines) + "\n"


def _embedding_result(
    model_spec: str,
    indexed: int,
    case_results: list[RetrievalCaseResult],
) -> EmbeddingEvaluationResult:
    return EmbeddingEvaluationResult(
        model_spec=model_spec,
        indexed_chunks=indexed,
        average_score=_average([case.score for case in case_results]),
        average_reciprocal_rank=_average([case.reciprocal_rank for case in case_results]),
        hit_rate=_average([1.0 if case.hit else 0.0 for case in case_results]),
        cases=case_results,
    )


def _best_embedding_result(
    results: list[EmbeddingEvaluationResult],
) -> EmbeddingEvaluationResult | None:
    if not results:
        return None
    return max(results, key=lambda result: (result.average_score, result.average_reciprocal_rank))


def _best_llm_model(results: list[LLMEvaluationResult]) -> str | None:
    successful = [result for result in results if result.error is None]
    if not successful:
        return None
    by_model = {
        model: mean(result.score for result in successful if result.model == model)
        for model in {result.model for result in successful}
    }
    return max(by_model, key=by_model.get)


def _failed_llm_results(
    model: str,
    retrieval_cases: list[RetrievalCaseResult],
    error: str,
) -> list[LLMEvaluationResult]:
    return [
        LLMEvaluationResult(
            model=model,
            case_id=case.case_id,
            pergunta=case.pergunta,
            score=0.0,
            answer="",
            latency_ms=0,
            error=error,
        )
        for case in retrieval_cases
    ]


def _can_run_any_llm(models: list[str]) -> bool:
    return any(
        os.getenv(name)
        for name in ["GROQ_API_KEY", "GEMINI_API_KEY"]
    )


def _reciprocal_rank(top_pages: list[int], expected_pages: list[int]) -> float:
    if not expected_pages:
        return 0.0
    expected = set(expected_pages)
    for index, page in enumerate(top_pages, start=1):
        if page in expected:
            return round(1.0 / index, 4)
    return 0.0


def _term_score(text: str, expected_terms: list[str]) -> float:
    if not expected_terms:
        return 0.0
    normalized = _normalize(text)
    hits = sum(1 for term in expected_terms if _normalize(term) in normalized)
    return hits / len(expected_terms)


def _citation_score(answer: str, expected_pages: list[int]) -> float:
    if not expected_pages:
        return 0.0
    normalized = _normalize(answer)
    hits = 0
    for page in expected_pages:
        patterns = [fr"p\.?\s*{page}\b", fr"pagina\s*{page}\b"]
        if any(re.search(pattern, normalized) for pattern in patterns):
            hits += 1
    return hits / len(expected_pages)


def _average(values: list[float]) -> float:
    return round(mean(values), 4) if values else 0.0


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in normalized if not unicodedata.combining(char))
