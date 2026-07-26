from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from time import perf_counter

from preparador_audiencia.chat import ChatResult, answer_process_question
from preparador_audiencia.evaluation import EvaluationCase, evaluate_retrieval_case
from preparador_audiencia.quality_signals import (
    extract_cited_pages,
    inspect_response_grounding,
)
from preparador_audiencia.question_router import QuestionRoute, route_question
from preparador_audiencia.repositories import ChunkRecord
from preparador_audiencia.retrieval import (
    ROUTED_QUERY_WEIGHT,
    search_process_queries_configured,
)
from preparador_audiencia.search import SearchResult
from preparador_audiencia.settings import (
    embedding_provider_from_environment,
    fallback_llm_from_environment,
    primary_llm_from_environment,
)

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
MIN_CASE_TEXT_CHARS = 180
MAX_EXPECTED_PAGES = 5

LEGAL_BENCHMARK_TERMS = {
    "acusacao",
    "acusado",
    "agressao",
    "alvara",
    "ameaca",
    "antecedentes",
    "apenado",
    "audiencia",
    "autuado",
    "cautelar",
    "cautelares",
    "certidao",
    "citacao",
    "crime",
    "criminal",
    "custodia",
    "decisao",
    "defesa",
    "defensoria",
    "delegado",
    "denuncia",
    "depoimento",
    "despacho",
    "domestica",
    "exame",
    "fianca",
    "flagrante",
    "intimacao",
    "interrogatorio",
    "instrucao",
    "judicial",
    "julgamento",
    "laudo",
    "lesao",
    "liberdade",
    "mandado",
    "medida",
    "medidas",
    "ministerio",
    "ofendido",
    "penal",
    "pericia",
    "policial",
    "prazo",
    "preventiva",
    "prisao",
    "protetiva",
    "protetivas",
    "prova",
    "provas",
    "publico",
    "relato",
    "sentenca",
    "testemunha",
    "testemunhas",
    "urgencia",
    "violencia",
    "vitima",
}

STOPWORDS = {
    "acesse",
    "assinado",
    "autos",
    "codigo",
    "comarca",
    "conferir",
    "documento",
    "estado",
    "fls",
    "informe",
    "justica",
    "numero",
    "original",
    "pagina",
    "processo",
    "protocolado",
    "site",
    "tjce",
    "tribunal",
    "vara",
    "para",
    "pela",
    "pelo",
    "como",
    "mais",
    "este",
    "esta",
    "esse",
    "essa",
    "sobre",
    "entre",
    "quando",
    "onde",
    "qual",
    "quais",
    "foram",
    "tendo",
}


@dataclass(frozen=True)
class RouteDetails:
    search_query: str
    area: str | None
    audiencia: str | None
    guide_ids: list[str]
    guide_titles: list[str]
    guide_scores: list[float]


@dataclass(frozen=True)
class RetrievalVariantResult:
    search_query: str
    pages: list[int]
    hit: bool
    reciprocal_rank: float
    term_coverage: float
    score: float
    latency_ms: int
    sources: list[dict[str, object]]


@dataclass(frozen=True)
class RoutingCaseResult:
    case_id: str
    pergunta: str
    expected_pages: list[int]
    expected_terms: list[str]
    route: RouteDetails
    raw: RetrievalVariantResult
    routed: RetrievalVariantResult
    outcome: str
    score_delta: float


@dataclass(frozen=True)
class LLMVariantResult:
    answer: str
    model: str | None
    fallback_used: bool
    latency_ms: int | None
    source_pages: list[int]
    citation_score: float
    term_score: float
    objective_score: float
    grounding_risk: str
    error: str | None


@dataclass(frozen=True)
class LLMCaseComparison:
    case_id: str
    pergunta: str
    raw: LLMVariantResult
    routed: LLMVariantResult
    outcome: str
    score_delta: float


@dataclass(frozen=True)
class RoutingBenchmarkReport:
    processo_id: str
    embedding_model: str
    top_k: int
    total_cases: int
    raw_hit_rate: float
    routed_hit_rate: float
    raw_mrr: float
    routed_mrr: float
    raw_average_score: float
    routed_average_score: float
    raw_average_latency_ms: float
    routed_average_latency_ms: float
    improved_cases: int
    degraded_cases: int
    tied_cases: int
    routed_cases_with_guides: int
    llm_fallback_count: int
    cases: list[RoutingCaseResult]
    llm_cases: list[LLMCaseComparison]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class _DiscardMessages:
    def add(self, *_args, **_kwargs) -> None:
        return None


def generate_cases_from_chunks(
    chunks: list[ChunkRecord],
    limit: int = 50,
) -> list[EvaluationCase]:
    if limit <= 0:
        return []
    token_pages = _token_pages(chunks)
    candidates: list[EvaluationCase] = []
    seen: set[tuple[str, tuple[int, ...]]] = set()

    for chunk in chunks:
        if len(chunk.text.strip()) < MIN_CASE_TEXT_CHARS:
            continue
        terms, expected_pages = _select_terms(chunk, token_pages)
        if (
            len(terms) < 2
            or not expected_pages
            or len(expected_pages) > MAX_EXPECTED_PAGES
        ):
            continue
        pergunta = _question_from_terms(terms)
        key = (pergunta, tuple(expected_pages))
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            EvaluationCase(
                id=f"auto_p{chunk.page_number:04d}_c{chunk.chunk_index:03d}",
                pergunta=pergunta,
                expected_pages=expected_pages,
                expected_terms=terms,
            )
        )

    return _select_evenly(candidates, limit)


def run_routing_benchmark(
    processo_id: str,
    cases: list[EvaluationCase],
    *,
    top_k: int = 5,
    embedding_model: str | None = None,
    llm_cases: int = 0,
    generator_model: str | None = None,
    fallback_model: str | None = None,
) -> RoutingBenchmarkReport:
    resolved_embedding = embedding_model or embedding_provider_from_environment()
    case_results = [
        _compare_retrieval_case(
            processo_id,
            case,
            top_k=top_k,
            embedding_model=resolved_embedding,
        )
        for case in cases
    ]
    llm_results = _compare_llm_cases(
        processo_id,
        cases[: max(0, llm_cases)],
        top_k=top_k,
        generator_model=generator_model or primary_llm_from_environment(),
        fallback_model=fallback_model or fallback_llm_from_environment(),
    )
    return RoutingBenchmarkReport(
        processo_id=processo_id,
        embedding_model=resolved_embedding,
        top_k=top_k,
        total_cases=len(case_results),
        raw_hit_rate=_rate(case_results, "raw", "hit"),
        routed_hit_rate=_rate(case_results, "routed", "hit"),
        raw_mrr=_average_variant(case_results, "raw", "reciprocal_rank"),
        routed_mrr=_average_variant(case_results, "routed", "reciprocal_rank"),
        raw_average_score=_average_variant(case_results, "raw", "score"),
        routed_average_score=_average_variant(case_results, "routed", "score"),
        raw_average_latency_ms=_average_variant(case_results, "raw", "latency_ms"),
        routed_average_latency_ms=_average_variant(case_results, "routed", "latency_ms"),
        improved_cases=sum(result.outcome == "melhorou" for result in case_results),
        degraded_cases=sum(result.outcome == "piorou" for result in case_results),
        tied_cases=sum(result.outcome == "empatou" for result in case_results),
        routed_cases_with_guides=sum(bool(result.route.guide_ids) for result in case_results),
        llm_fallback_count=sum(
            variant.fallback_used
            for comparison in llm_results
            for variant in (comparison.raw, comparison.routed)
        ),
        cases=case_results,
        llm_cases=llm_results,
    )


def write_routing_benchmark_report(
    report: RoutingBenchmarkReport,
    output_path: str | Path,
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    path.with_suffix(".md").write_text(
        render_routing_benchmark_markdown(report),
        encoding="utf-8",
    )


def render_routing_benchmark_markdown(report: RoutingBenchmarkReport) -> str:
    lines = [
        "# Benchmark A/B da triagem interna",
        "",
        f"Processo: `{report.processo_id}`",
        "",
        f"Recuperador: `{report.embedding_model}`",
        "",
        f"Casos: `{report.total_cases}`",
        "",
        f"Top K: `{report.top_k}`",
        "",
        "## Resultado",
        "",
        "| Metrica | Pergunta bruta | Com triagem |",
        "|---|---:|---:|",
        f"| Hit rate | {report.raw_hit_rate:.4f} | {report.routed_hit_rate:.4f} |",
        f"| MRR | {report.raw_mrr:.4f} | {report.routed_mrr:.4f} |",
        (
            f"| Score medio | {report.raw_average_score:.4f} | "
            f"{report.routed_average_score:.4f} |"
        ),
        (
            f"| Latencia media | {report.raw_average_latency_ms:.2f} ms | "
            f"{report.routed_average_latency_ms:.2f} ms |"
        ),
        "",
        f"Casos que melhoraram: `{report.improved_cases}`",
        "",
        f"Casos que pioraram: `{report.degraded_cases}`",
        "",
        f"Empates: `{report.tied_cases}`",
        "",
        f"Casos com guia selecionado: `{report.routed_cases_with_guides}`",
        "",
        f"Fallbacks nas comparacoes LLM: `{report.llm_fallback_count}`",
        "",
        "## Recuperacao por caso",
        "",
        "| Caso | Esperado | Bruta | Triagem | Delta | Resultado | Guias |",
        "|---|---|---|---|---:|---|---|",
    ]
    for result in report.cases:
        lines.append(
            f"| `{result.case_id}` | {_pages(result.expected_pages)} | "
            f"{_pages(result.raw.pages)} | {_pages(result.routed.pages)} | "
            f"{result.score_delta:+.4f} | {result.outcome} | "
            f"{'; '.join(result.route.guide_titles[:2])} |"
        )
    if report.llm_cases:
        lines.extend(
            [
                "",
                "## Respostas LLM",
                "",
                "| Caso | Score bruto | Score triagem | Delta | Resultado | Modelos |",
                "|---|---:|---:|---:|---|---|",
            ]
        )
        for result in report.llm_cases:
            lines.append(
                f"| `{result.case_id}` | {result.raw.objective_score:.4f} | "
                f"{result.routed.objective_score:.4f} | {result.score_delta:+.4f} | "
                f"{result.outcome} | {result.raw.model} / {result.routed.model} |"
            )
    return "\n".join(lines) + "\n"


def _compare_retrieval_case(
    processo_id: str,
    case: EvaluationCase,
    *,
    top_k: int,
    embedding_model: str,
) -> RoutingCaseResult:
    route = route_question(case.pergunta)
    raw = _search_variant(processo_id, case, case.pergunta, top_k, embedding_model)
    routed = _search_routed_variant(
        processo_id,
        case,
        route,
        top_k,
        embedding_model,
    )
    delta = round(routed.score - raw.score, 4)
    return RoutingCaseResult(
        case_id=case.id,
        pergunta=case.pergunta,
        expected_pages=case.expected_pages,
        expected_terms=case.expected_terms,
        route=_route_details(route),
        raw=raw,
        routed=routed,
        outcome=_outcome(delta),
        score_delta=delta,
    )


def _search_variant(
    processo_id: str,
    case: EvaluationCase,
    query: str,
    top_k: int,
    embedding_model: str,
) -> RetrievalVariantResult:
    started = perf_counter()
    sources = search_process_queries_configured(
        processo_id=processo_id,
        queries=[(query, 1.0)],
        top_k=top_k,
        embedding_spec=embedding_model,
    )
    latency_ms = round((perf_counter() - started) * 1000)
    return _retrieval_result(case, query, sources, latency_ms)


def _search_routed_variant(
    processo_id: str,
    case: EvaluationCase,
    route: QuestionRoute,
    top_k: int,
    embedding_model: str,
) -> RetrievalVariantResult:
    started = perf_counter()
    routed_query = route.search_query()
    sources = search_process_queries_configured(
        processo_id=processo_id,
        queries=[
            (case.pergunta, 1.0),
            (routed_query, ROUTED_QUERY_WEIGHT),
        ],
        top_k=top_k,
        embedding_spec=embedding_model,
    )
    latency_ms = round((perf_counter() - started) * 1000)
    return _retrieval_result(
        case,
        routed_query,
        sources,
        latency_ms,
    )


def _retrieval_result(
    case: EvaluationCase,
    query: str,
    sources: list[SearchResult],
    latency_ms: int,
) -> RetrievalVariantResult:
    evaluated = evaluate_retrieval_case(case, sources)
    term_coverage = _term_score(
        " ".join(source.text for source in sources),
        case.expected_terms,
    )
    score = round(
        (0.6 * float(evaluated.hit))
        + (0.25 * evaluated.reciprocal_rank)
        + (0.15 * term_coverage),
        4,
    )
    return RetrievalVariantResult(
        search_query=query,
        pages=evaluated.top_pages,
        hit=evaluated.hit,
        reciprocal_rank=evaluated.reciprocal_rank,
        term_coverage=term_coverage,
        score=score,
        latency_ms=latency_ms,
        sources=_source_summaries(sources),
    )


def _compare_llm_cases(
    processo_id: str,
    cases: list[EvaluationCase],
    *,
    top_k: int,
    generator_model: str,
    fallback_model: str,
) -> list[LLMCaseComparison]:
    messages = _DiscardMessages()
    comparisons = []
    for case in cases:
        raw_result = answer_process_question(
            processo_id=processo_id,
            pergunta=case.pergunta,
            messages=messages,
            top_k=top_k,
            primary_model=generator_model,
            fallback_model=fallback_model,
            use_question_routing=False,
        )
        routed_result = answer_process_question(
            processo_id=processo_id,
            pergunta=case.pergunta,
            messages=messages,
            top_k=top_k,
            primary_model=generator_model,
            fallback_model=fallback_model,
            use_question_routing=True,
        )
        raw = _llm_variant(case, raw_result)
        routed = _llm_variant(case, routed_result)
        delta = round(routed.objective_score - raw.objective_score, 4)
        comparisons.append(
            LLMCaseComparison(
                case_id=case.id,
                pergunta=case.pergunta,
                raw=raw,
                routed=routed,
                outcome=_outcome(delta),
                score_delta=delta,
            )
        )
    return comparisons


def _llm_variant(case: EvaluationCase, result: ChatResult) -> LLMVariantResult:
    citation_score = _citation_score(result.resposta, case.expected_pages)
    term_score = _term_score(result.resposta, case.expected_terms)
    grounding = inspect_response_grounding(result.resposta, result.fontes)
    return LLMVariantResult(
        answer=result.resposta,
        model=result.modelo,
        fallback_used=result.fallback_usado,
        latency_ms=result.latency_ms,
        source_pages=sorted({source.page_number for source in result.fontes}),
        citation_score=citation_score,
        term_score=term_score,
        objective_score=round((0.55 * citation_score) + (0.45 * term_score), 4),
        grounding_risk=grounding.rule_risk,
        error=result.erro,
    )


def _token_pages(chunks: list[ChunkRecord]) -> dict[str, set[int]]:
    pages: dict[str, set[int]] = {}
    for chunk in chunks:
        for token in _benchmark_tokens(chunk.text):
            pages.setdefault(token, set()).add(chunk.page_number)
    return pages


def _select_terms(
    chunk: ChunkRecord,
    token_pages: dict[str, set[int]],
) -> tuple[list[str], list[int]]:
    ranked = sorted(
        _benchmark_tokens(chunk.text),
        key=lambda token: (
            len(token_pages.get(token, set())),
            -chunk.text.lower().count(token),
            -len(token),
            token,
        ),
    )
    selected: list[str] = []
    expected_pages: set[int] | None = None
    for token in ranked:
        pages = token_pages.get(token, set())
        if chunk.page_number not in pages:
            continue
        intersection = pages if expected_pages is None else expected_pages.intersection(pages)
        if not intersection:
            continue
        selected.append(token)
        expected_pages = set(intersection)
        if len(selected) >= 2 and len(expected_pages) <= MAX_EXPECTED_PAGES:
            break
    return selected[:3], sorted(expected_pages or [])


def _tokens(text: str) -> set[str]:
    normalized = _normalize(text)
    return {
        token
        for token in TOKEN_PATTERN.findall(normalized)
        if 4 <= len(token) <= 24
        and token not in STOPWORDS
        and not token.isdigit()
        and not (any(char.isdigit() for char in token) and len(token) >= 10)
    }


def _benchmark_tokens(text: str) -> set[str]:
    return _tokens(text).intersection(LEGAL_BENCHMARK_TERMS)


def _question_from_terms(terms: list[str]) -> str:
    if len(terms) == 2:
        subject = f"{terms[0]} e {terms[1]}"
    else:
        subject = ", ".join(terms[:-1]) + f" e {terms[-1]}"
    return f"O que o processo informa sobre {subject} e em qual contexto isso aparece?"


def _select_evenly(cases: list[EvaluationCase], limit: int) -> list[EvaluationCase]:
    if len(cases) <= limit:
        return cases
    if limit == 1:
        return [cases[len(cases) // 2]]
    indexes = {
        round(index * (len(cases) - 1) / (limit - 1))
        for index in range(limit)
    }
    return [cases[index] for index in sorted(indexes)]


def _route_details(route: QuestionRoute) -> RouteDetails:
    return RouteDetails(
        search_query=route.search_query(),
        area=route.area,
        audiencia=route.audiencia,
        guide_ids=[guide.id for guide in route.guides],
        guide_titles=[guide.titulo for guide in route.guides],
        guide_scores=[guide.score for guide in route.guides],
    )


def _source_summaries(sources: list[SearchResult]) -> list[dict[str, object]]:
    return [
        {
            "page": source.page_number,
            "chunk_index": source.chunk_index,
            "score": source.score,
            "document_type": source.document_type,
        }
        for source in sources
    ]


def _term_score(text: str, terms: list[str]) -> float:
    if not terms:
        return 0.0
    normalized = _normalize(text)
    return round(sum(_normalize(term) in normalized for term in terms) / len(terms), 4)


def _citation_score(answer: str, expected_pages: list[int]) -> float:
    if not expected_pages:
        return 0.0
    cited = set(extract_cited_pages(answer))
    return round(len(cited.intersection(expected_pages)) / len(set(expected_pages)), 4)


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    without_accents = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return " ".join(without_accents.split())


def _outcome(delta: float) -> str:
    if delta > 0.0001:
        return "melhorou"
    if delta < -0.0001:
        return "piorou"
    return "empatou"


def _rate(
    results: list[RoutingCaseResult],
    variant_name: str,
    field_name: str,
) -> float:
    if not results:
        return 0.0
    values = [
        float(getattr(getattr(result, variant_name), field_name))
        for result in results
    ]
    return round(mean(values), 4)


def _average_variant(
    results: list[RoutingCaseResult],
    variant_name: str,
    field_name: str,
) -> float:
    return _rate(results, variant_name, field_name)


def _pages(pages: list[int]) -> str:
    return ", ".join(str(page) for page in pages)
