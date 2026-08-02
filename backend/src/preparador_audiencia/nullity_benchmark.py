from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean

from preparador_audiencia.nullity_analysis import (
    NullityAnalysisResult,
    analyze_recognition_sources,
)
from preparador_audiencia.search import SearchResult

DEFAULT_NULLITY_BENCHMARK_PATH = (
    Path(__file__).resolve().parents[2] / "data/nullity_benchmark_recognition.json"
)
DISABLED_BENCHMARK_FALLBACK = "benchmark-disabled:no-fallback"
VALID_CONCLUSIONS = {
    "forte_fundamento_para_alegar_invalidade",
    "procedimento_aparentemente_regular",
    "inconclusivo",
    "reconhecimento_nao_localizado",
    "rito_formal_nao_aplicavel",
}
VALID_IMPACTS = {
    "reconhecimento_determinante_sem_prova_independente",
    "ha_indicios_de_prova_independente",
    "inconclusivo",
    "nao_aplicavel",
}
VALID_REQUIREMENT_RESULTS = {
    "observado",
    "nao_observado",
    "nao_localizado",
    "nao_aplicavel",
}


@dataclass(frozen=True)
class NullityBenchmarkExpectation:
    conclusion: str
    procedural_impact: str
    requirement_results: dict[str, str]
    requirement_pages: dict[str, tuple[int, ...]]
    impact_pages: tuple[int, ...]


@dataclass(frozen=True)
class NullityBenchmarkCase:
    id: str
    title: str
    sources: tuple[SearchResult, ...]
    expected: NullityBenchmarkExpectation


@dataclass(frozen=True)
class NullityBenchmarkSuite:
    id: str
    description: str
    legal_review_status: str
    cases: tuple[NullityBenchmarkCase, ...]


@dataclass(frozen=True)
class NullityBenchmarkCaseResult:
    case_id: str
    title: str
    requested_model: str
    actual_model: str | None
    elapsed_ms: int
    expected_conclusion: str
    predicted_conclusion: str | None
    conclusion_correct: bool
    expected_impact: str
    predicted_impact: str | None
    impact_correct: bool
    requirements_correct: int
    requirements_total: int
    page_references_correct: int
    page_references_total: int
    weighted_score: float
    false_positive_invalidity: bool
    analysis: dict[str, object] | None
    error: str | None


@dataclass(frozen=True)
class NullityBenchmarkModelResult:
    model: str
    cases_count: int
    errors_count: int
    conclusion_accuracy: float
    impact_accuracy: float
    requirement_accuracy: float
    page_reference_accuracy: float
    average_weighted_score: float
    average_elapsed_ms: float
    false_positive_invalidity_count: int
    gate_passed: bool
    cases: tuple[NullityBenchmarkCaseResult, ...]


@dataclass(frozen=True)
class NullityBenchmarkReport:
    suite_id: str
    suite_description: str
    legal_review_status: str
    generated_at: str
    models: tuple[NullityBenchmarkModelResult, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


Analyzer = Callable[..., NullityAnalysisResult]


def load_nullity_benchmark_suite(
    path: str | Path | None = None,
) -> NullityBenchmarkSuite:
    benchmark_path = Path(path) if path is not None else DEFAULT_NULLITY_BENCHMARK_PATH
    payload = json.loads(benchmark_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("Schema de benchmark de nulidade nao suportado.")
    cases = tuple(_case_from_dict(item) for item in payload["cases"])
    suite = NullityBenchmarkSuite(
        id=str(payload["id"]),
        description=str(payload["description"]),
        legal_review_status=str(payload["legal_review_status"]),
        cases=cases,
    )
    _validate_suite(suite)
    return suite


def run_nullity_benchmark(
    suite: NullityBenchmarkSuite,
    models: list[str],
    *,
    analyzer: Analyzer = analyze_recognition_sources,
    delay_seconds: float = 0.0,
) -> NullityBenchmarkReport:
    if not models:
        raise ValueError("Informe pelo menos um modelo para o benchmark.")
    model_results = []
    for model in models:
        case_results = []
        for index, case in enumerate(suite.cases):
            case_result = _run_case(case, model, analyzer)
            case_results.append(case_result)
            has_next_case = index < len(suite.cases) - 1
            if (
                delay_seconds > 0
                and has_next_case
                and case_result.actual_model != "sistema"
            ):
                time.sleep(delay_seconds)
        model_results.append(_summarize_model(model, case_results))
    return NullityBenchmarkReport(
        suite_id=suite.id,
        suite_description=suite.description,
        legal_review_status=suite.legal_review_status,
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        models=tuple(model_results),
    )


def write_nullity_benchmark_report(
    report: NullityBenchmarkReport,
    output_path: str | Path,
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    path.with_suffix(".md").write_text(
        render_nullity_benchmark_markdown(report),
        encoding="utf-8",
    )


def render_nullity_benchmark_markdown(report: NullityBenchmarkReport) -> str:
    lines = [
        "# Benchmark de nulidade no reconhecimento",
        "",
        f"Suite: `{report.suite_id}`",
        "",
        f"Status da revisao juridica: `{report.legal_review_status}`",
        "",
        report.suite_description,
        "",
        (
            "Este resultado mede concordancia com rotulos tecnicos controlados. "
            "Ele nao substitui a revisao de um defensor."
        ),
        "",
        "## Resultado por modelo",
        "",
        (
            "| Modelo | Conclusao | Impacto | Requisitos | Paginas | Nota | "
            "Falsos positivos | Erros | Gate |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for model in report.models:
        lines.append(
            "| "
            f"`{model.model}` | "
            f"{model.conclusion_accuracy:.1%} | "
            f"{model.impact_accuracy:.1%} | "
            f"{model.requirement_accuracy:.1%} | "
            f"{model.page_reference_accuracy:.1%} | "
            f"{model.average_weighted_score:.1f} | "
            f"{model.false_positive_invalidity_count} | "
            f"{model.errors_count} | "
            f"{'aprovado' if model.gate_passed else 'reprovado'} |"
        )
    for model in report.models:
        lines.extend(["", f"## {model.model}", ""])
        for case in model.cases:
            status = "correto" if case.conclusion_correct else "divergente"
            lines.extend(
                [
                    f"### {case.title}",
                    "",
                    f"Caso: `{case.case_id}`",
                    "",
                    f"Conclusao: `{case.predicted_conclusion or 'erro'}` ({status})",
                    "",
                    f"Impacto: `{case.predicted_impact or 'erro'}`",
                    "",
                    f"Nota ponderada: `{case.weighted_score:.1f}`",
                    "",
                    f"Tempo: `{case.elapsed_ms} ms`",
                ]
            )
            if case.error:
                lines.extend(["", f"Erro: {case.error}"])
            elif case.analysis:
                lines.extend(["", f"Resumo: {case.analysis.get('resumo', '')}"])
    return "\n".join(lines) + "\n"


def estimate_nullity_llm_calls(cases_count: int, models_count: int) -> int:
    return max(0, cases_count) * max(0, models_count)


def _run_case(
    case: NullityBenchmarkCase,
    model: str,
    analyzer: Analyzer,
) -> NullityBenchmarkCaseResult:
    started = time.perf_counter()
    try:
        analysis = analyzer(
            list(case.sources),
            primary_model=model,
            fallback_model=DISABLED_BENCHMARK_FALLBACK,
        )
    except Exception as exc:
        return _error_case_result(case, model, _elapsed_ms(started), str(exc))
    return _score_case(case, model, analysis, _elapsed_ms(started))


def _score_case(
    case: NullityBenchmarkCase,
    model: str,
    analysis: NullityAnalysisResult,
    elapsed_ms: int,
) -> NullityBenchmarkCaseResult:
    expected = case.expected
    conclusion_correct = analysis.conclusion == expected.conclusion
    impact_correct = analysis.procedural_impact == expected.procedural_impact
    predicted_requirements = {item.id: item for item in analysis.requirements}
    requirements_total = len(expected.requirement_results)
    requirements_correct = sum(
        1
        for requirement_id, expected_result in expected.requirement_results.items()
        if predicted_requirements.get(requirement_id)
        and predicted_requirements[requirement_id].result == expected_result
    )
    page_references_correct, page_references_total = _score_page_references(
        expected,
        predicted_requirements,
        analysis,
    )
    weighted_total = 7 + requirements_total + page_references_total
    weighted_correct = (
        (5 if conclusion_correct else 0)
        + (2 if impact_correct else 0)
        + requirements_correct
        + page_references_correct
    )
    score = round((weighted_correct / weighted_total) * 100, 2)
    false_positive = (
        analysis.conclusion == "forte_fundamento_para_alegar_invalidade"
        and expected.conclusion != "forte_fundamento_para_alegar_invalidade"
    )
    return NullityBenchmarkCaseResult(
        case_id=case.id,
        title=case.title,
        requested_model=model,
        actual_model=analysis.model,
        elapsed_ms=elapsed_ms,
        expected_conclusion=expected.conclusion,
        predicted_conclusion=analysis.conclusion,
        conclusion_correct=conclusion_correct,
        expected_impact=expected.procedural_impact,
        predicted_impact=analysis.procedural_impact,
        impact_correct=impact_correct,
        requirements_correct=requirements_correct,
        requirements_total=requirements_total,
        page_references_correct=page_references_correct,
        page_references_total=page_references_total,
        weighted_score=score,
        false_positive_invalidity=false_positive,
        analysis=_analysis_to_dict(analysis),
        error=None,
    )


def _score_page_references(
    expected: NullityBenchmarkExpectation,
    predicted_requirements: dict[str, object],
    analysis: NullityAnalysisResult,
) -> tuple[int, int]:
    correct = 0
    total = 0
    for requirement_id, expected_pages in expected.requirement_pages.items():
        if not expected_pages:
            continue
        total += 1
        assessment = predicted_requirements.get(requirement_id)
        if assessment and set(assessment.pages).intersection(expected_pages):
            correct += 1
    if expected.impact_pages:
        total += 1
        if set(analysis.impact_pages).intersection(expected.impact_pages):
            correct += 1
    return correct, total


def _summarize_model(
    model: str,
    cases: list[NullityBenchmarkCaseResult],
) -> NullityBenchmarkModelResult:
    conclusion_accuracy = _ratio(sum(item.conclusion_correct for item in cases), len(cases))
    impact_accuracy = _ratio(sum(item.impact_correct for item in cases), len(cases))
    requirements_correct = sum(item.requirements_correct for item in cases)
    requirements_total = sum(item.requirements_total for item in cases)
    pages_correct = sum(item.page_references_correct for item in cases)
    pages_total = sum(item.page_references_total for item in cases)
    false_positives = sum(item.false_positive_invalidity for item in cases)
    errors = sum(item.error is not None for item in cases)
    requirement_accuracy = _ratio(requirements_correct, requirements_total)
    page_accuracy = _ratio(pages_correct, pages_total)
    return NullityBenchmarkModelResult(
        model=model,
        cases_count=len(cases),
        errors_count=errors,
        conclusion_accuracy=conclusion_accuracy,
        impact_accuracy=impact_accuracy,
        requirement_accuracy=requirement_accuracy,
        page_reference_accuracy=page_accuracy,
        average_weighted_score=round(mean(item.weighted_score for item in cases), 2),
        average_elapsed_ms=round(mean(item.elapsed_ms for item in cases), 2),
        false_positive_invalidity_count=false_positives,
        gate_passed=(
            errors == 0
            and false_positives == 0
            and conclusion_accuracy >= 0.8
            and requirement_accuracy >= 0.8
            and page_accuracy >= 0.9
        ),
        cases=tuple(cases),
    )


def _analysis_to_dict(analysis: NullityAnalysisResult) -> dict[str, object]:
    return {
        "conclusao": analysis.conclusion,
        "confianca": analysis.confidence,
        "resumo": analysis.summary,
        "aplicabilidade": analysis.applicability,
        "justificativa_aplicabilidade": analysis.applicability_summary,
        "impacto_processual": analysis.procedural_impact,
        "justificativa_impacto": analysis.impact_summary,
        "paginas_impacto": list(analysis.impact_pages),
        "requisitos": [asdict(item) for item in analysis.requirements],
        "providencias": list(analysis.next_steps),
        "lacunas": list(analysis.gaps),
        "avisos": list(analysis.warnings),
    }


def _error_case_result(
    case: NullityBenchmarkCase,
    model: str,
    elapsed_ms: int,
    error: str,
) -> NullityBenchmarkCaseResult:
    return NullityBenchmarkCaseResult(
        case_id=case.id,
        title=case.title,
        requested_model=model,
        actual_model=None,
        elapsed_ms=elapsed_ms,
        expected_conclusion=case.expected.conclusion,
        predicted_conclusion=None,
        conclusion_correct=False,
        expected_impact=case.expected.procedural_impact,
        predicted_impact=None,
        impact_correct=False,
        requirements_correct=0,
        requirements_total=len(case.expected.requirement_results),
        page_references_correct=0,
        page_references_total=(
            sum(bool(pages) for pages in case.expected.requirement_pages.values())
            + bool(case.expected.impact_pages)
        ),
        weighted_score=0.0,
        false_positive_invalidity=False,
        analysis=None,
        error=error,
    )


def _case_from_dict(item: dict[str, object]) -> NullityBenchmarkCase:
    expected = item["expected"]
    return NullityBenchmarkCase(
        id=str(item["id"]),
        title=str(item["title"]),
        sources=tuple(_source_from_dict(source) for source in item["sources"]),
        expected=NullityBenchmarkExpectation(
            conclusion=str(expected["conclusion"]),
            procedural_impact=str(expected["procedural_impact"]),
            requirement_results={
                str(key): str(value)
                for key, value in expected["requirement_results"].items()
            },
            requirement_pages={
                str(key): tuple(int(page) for page in pages)
                for key, pages in expected.get("requirement_pages", {}).items()
            },
            impact_pages=tuple(int(page) for page in expected.get("impact_pages", [])),
        ),
    )


def _source_from_dict(item: dict[str, object]) -> SearchResult:
    return SearchResult(
        text=str(item["text"]),
        page_number=int(item["page"]),
        chunk_index=int(item["chunk_index"]),
        document_type=str(item["document_type"]) if item.get("document_type") else None,
        score=1.0,
        source_confidence=str(item.get("source_confidence", "alta")),
    )


def _validate_suite(suite: NullityBenchmarkSuite) -> None:
    if not suite.cases:
        raise ValueError("O benchmark precisa de pelo menos um caso.")
    case_ids = [case.id for case in suite.cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("O benchmark contem casos duplicados.")
    for case in suite.cases:
        if case.expected.conclusion not in VALID_CONCLUSIONS:
            raise ValueError(f"Conclusao esperada invalida no caso {case.id}.")
        if case.expected.procedural_impact not in VALID_IMPACTS:
            raise ValueError(f"Impacto esperado invalido no caso {case.id}.")
        if not set(case.expected.requirement_results.values()) <= VALID_REQUIREMENT_RESULTS:
            raise ValueError(f"Resultado de requisito invalido no caso {case.id}.")
        source_pages = {source.page_number for source in case.sources}
        referenced_pages = {
            page
            for pages in case.expected.requirement_pages.values()
            for page in pages
        } | set(case.expected.impact_pages)
        if not referenced_pages <= source_pages:
            raise ValueError(f"O caso {case.id} referencia pagina sem fonte controlada.")


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 1.0


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
