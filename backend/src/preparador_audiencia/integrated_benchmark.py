from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

SCHEMA_VERSION = "1.0"
VALID_SPLITS = frozenset({"development", "test"})
VALID_REVIEW_STATUSES = frozenset(
    {"pending", "technical_review", "legal_approved", "rejected"}
)
VALID_PROVENANCE = frozenset({"synthetic", "anonymized_real", "public_real"})
ITEM_ALTERNATIVE_SEPARATOR = "||"


@dataclass(frozen=True)
class QualityGate:
    min_label_accuracy: float | None = None
    min_page_precision: float | None = None
    min_page_recall: float | None = None
    min_page_hit_rate: float | None = None
    min_citation_fidelity: float | None = None
    min_item_recall: float | None = None
    min_abstention_accuracy: float | None = None
    max_false_positive_case_rate: float | None = None
    max_error_rate: float | None = None
    max_p95_latency_ms: int | None = None
    max_average_llm_calls: float | None = None


@dataclass(frozen=True)
class CaseExpectation:
    label: str | None = None
    relevant_pages: tuple[int, ...] | None = None
    required_items: tuple[str, ...] | None = None
    forbidden_items: tuple[str, ...] | None = None
    should_abstain: bool | None = None


@dataclass(frozen=True)
class BenchmarkSource:
    reference_id: str
    document: str
    title: str | None
    url: str | None
    sha256: str | None
    text_sha256: str | None = None


@dataclass(frozen=True)
class IntegratedBenchmarkCase:
    id: str
    engine: str
    split: str
    provenance: str
    review_status: str
    description: str
    tags: tuple[str, ...]
    source: BenchmarkSource | None
    expected: CaseExpectation

    @property
    def eligible_for_gate(self) -> bool:
        return self.split == "test" and self.review_status == "legal_approved"


@dataclass(frozen=True)
class IntegratedBenchmarkSuite:
    id: str
    description: str
    cases: tuple[IntegratedBenchmarkCase, ...]
    default_gate: QualityGate
    engine_gates: dict[str, QualityGate]


@dataclass(frozen=True)
class ObservationSource:
    page: int
    chunk_index: int
    text: str


@dataclass(frozen=True)
class CaseObservation:
    case_id: str
    label: str | None
    source_pages: tuple[int, ...] | None
    cited_pages: tuple[int, ...] | None
    items: tuple[str, ...] | None
    abstained: bool | None
    latency_ms: int | None
    llm_calls: int
    prompt_tokens: int | None
    completion_tokens: int | None
    estimated_cost_usd: float | None
    error: str | None
    model: str | None = None
    fallback_used: bool | None = None
    response: str | None = None
    sources: tuple[ObservationSource, ...] = ()


@dataclass(frozen=True)
class ObservationRun:
    suite_id: str
    run_id: str
    producer: str
    generated_at: str
    observations: tuple[CaseObservation, ...]


@dataclass(frozen=True)
class IntegratedCaseResult:
    case_id: str
    engine: str
    split: str
    provenance: str
    review_status: str
    eligible_for_gate: bool
    label_correct: bool | None
    page_precision: float | None
    page_recall: float | None
    page_hit: bool | None
    citation_fidelity: float | None
    item_recall: float | None
    false_positive: bool | None
    unexpected_items: tuple[str, ...]
    abstention_correct: bool | None
    latency_ms: int | None
    llm_calls: int
    prompt_tokens: int | None
    completion_tokens: int | None
    estimated_cost_usd: float | None
    error: str | None
    model: str | None = None
    fallback_used: bool | None = None
    response: str | None = None
    source_pages: tuple[int, ...] = ()
    cited_pages: tuple[int, ...] = ()
    observed_items: tuple[str, ...] = ()
    sources: tuple[ObservationSource, ...] = ()


@dataclass(frozen=True)
class QualityMetrics:
    cases_count: int
    label_accuracy: float | None
    page_precision: float | None
    page_recall: float | None
    page_hit_rate: float | None
    citation_fidelity: float | None
    item_recall: float | None
    abstention_accuracy: float | None
    false_positive_case_rate: float | None
    error_rate: float
    p50_latency_ms: int | None
    p95_latency_ms: int | None
    total_llm_calls: int
    average_llm_calls: float
    prompt_tokens: int | None
    completion_tokens: int | None
    estimated_cost_usd: float | None


@dataclass(frozen=True)
class EngineBenchmarkResult:
    engine: str
    metrics: QualityMetrics
    gate_metrics: QualityMetrics | None
    gate_status: str
    failed_checks: tuple[str, ...]
    cases: tuple[IntegratedCaseResult, ...]


@dataclass(frozen=True)
class IntegratedBenchmarkReport:
    suite_id: str
    run_id: str
    producer: str
    split: str
    generated_at: str
    cases_count: int
    legal_approved_cases: int
    gate_status: str
    engines: tuple[EngineBenchmarkResult, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def load_integrated_benchmark_suite(path: str | Path) -> IntegratedBenchmarkSuite:
    payload = _load_mapping(path)
    _require_schema(payload)
    cases = tuple(_case_from_dict(item) for item in _require_list(payload, "cases"))
    if not cases:
        raise ValueError("A suite integrada precisa conter pelo menos um caso.")
    _ensure_unique((case.id for case in cases), "caso")
    gates = _require_mapping(payload.get("gates", {}), "gates")
    default_gate = _gate_from_dict(_require_mapping(gates.get("default", {}), "gates.default"))
    engine_gates = {
        str(engine): _gate_from_dict(_require_mapping(value, f"gates.{engine}"))
        for engine, value in _require_mapping(gates.get("engines", {}), "gates.engines").items()
    }
    return IntegratedBenchmarkSuite(
        id=_require_text(payload, "id"),
        description=_optional_text(payload.get("description")),
        cases=cases,
        default_gate=default_gate,
        engine_gates=engine_gates,
    )


def load_observation_run(path: str | Path) -> ObservationRun:
    payload = _load_mapping(path)
    _require_schema(payload)
    observations = tuple(
        _observation_from_dict(item) for item in _require_list(payload, "observations")
    )
    _ensure_unique((item.case_id for item in observations), "observacao")
    return ObservationRun(
        suite_id=_require_text(payload, "suite_id"),
        run_id=_require_text(payload, "run_id"),
        producer=_require_text(payload, "producer"),
        generated_at=_require_text(payload, "generated_at"),
        observations=observations,
    )


def write_integrated_benchmark_suite(
    suite: IntegratedBenchmarkSuite,
    path: str | Path,
) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "id": suite.id,
        "description": suite.description,
        "gates": {
            "default": asdict(suite.default_gate),
            "engines": {
                engine: asdict(gate) for engine, gate in suite.engine_gates.items()
            },
        },
        "cases": [
            {
                "id": case.id,
                "engine": case.engine,
                "split": case.split,
                "provenance": case.provenance,
                "review_status": case.review_status,
                "description": case.description,
                "tags": list(case.tags),
                "source": asdict(case.source) if case.source is not None else None,
                "expected": asdict(case.expected),
            }
            for case in suite.cases
        ],
    }
    _write_json(payload, path)


def write_observation_run(run: ObservationRun, path: str | Path) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "suite_id": run.suite_id,
        "run_id": run.run_id,
        "producer": run.producer,
        "generated_at": run.generated_at,
        "observations": [asdict(item) for item in run.observations],
    }
    _write_json(payload, path)


def run_integrated_benchmark(
    suite: IntegratedBenchmarkSuite,
    observation_run: ObservationRun,
    *,
    split: str = "development",
    case_ids: set[str] | None = None,
) -> IntegratedBenchmarkReport:
    if split not in VALID_SPLITS:
        raise ValueError(f"Split invalido: {split}")
    if observation_run.suite_id != suite.id:
        raise ValueError("As observacoes pertencem a outra suite.")
    suite_ids = {case.id for case in suite.cases}
    unknown = {item.case_id for item in observation_run.observations} - suite_ids
    if unknown:
        raise ValueError("Observacoes desconhecidas: " + ", ".join(sorted(unknown)))

    selected = [
        case
        for case in suite.cases
        if case.split == split
        and case.review_status != "rejected"
        and (case_ids is None or case.id in case_ids)
    ]
    if case_ids is not None:
        missing = case_ids - {case.id for case in selected}
        if missing:
            raise ValueError("Casos nao encontrados no split: " + ", ".join(sorted(missing)))
    if not selected:
        raise ValueError(f"Nenhum caso executavel no split {split}.")

    observation_by_id = {item.case_id: item for item in observation_run.observations}
    results = tuple(
        _score_case(case, observation_by_id.get(case.id)) for case in selected
    )
    engines = tuple(
        _summarize_engine(engine, results, suite)
        for engine in sorted({result.engine for result in results})
    )
    statuses = {engine.gate_status for engine in engines}
    if "failed" in statuses:
        gate_status = "failed"
    elif statuses == {"passed"}:
        gate_status = "passed"
    else:
        gate_status = "not_eligible"
    return IntegratedBenchmarkReport(
        suite_id=suite.id,
        run_id=observation_run.run_id,
        producer=observation_run.producer,
        split=split,
        generated_at=datetime.now(UTC).isoformat(),
        cases_count=len(results),
        legal_approved_cases=sum(item.eligible_for_gate for item in results),
        gate_status=gate_status,
        engines=engines,
    )


def write_integrated_benchmark_report(
    report: IntegratedBenchmarkReport,
    output_path: str | Path,
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    path.with_suffix(".md").write_text(
        render_integrated_benchmark_markdown(report),
        encoding="utf-8",
    )


def render_integrated_benchmark_markdown(report: IntegratedBenchmarkReport) -> str:
    lines = [
        "# Benchmark integrado de qualidade",
        "",
        f"Suite: `{report.suite_id}`",
        "",
        f"Execucao: `{report.run_id}`",
        "",
        f"Produtor das observacoes: `{report.producer}`",
        "",
        f"Split: `{report.split}`",
        "",
        f"Casos: `{report.cases_count}`",
        "",
        f"Casos aprovados juridicamente: `{report.legal_approved_cases}`",
        "",
        f"Gate geral: `{report.gate_status}`",
        "",
    ]
    if report.gate_status == "not_eligible":
        if report.producer == "calibration_fixture":
            notice = (
                "Este relatorio calibra a infraestrutura de avaliacao. Ele nao "
                "aprova a qualidade juridica porque usa observacoes sinteticas."
            )
        else:
            notice = (
                "Este relatorio usa observacoes produzidas por uma execucao real, "
                "mas nao aprova a qualidade juridica porque nao ha casos de teste "
                "com revisao juridica aprovada."
            )
        lines.extend([notice, ""])
    lines.extend(
        [
            "## Resultado por motor",
            "",
            (
                "| Motor | Casos | Rotulo | Precisao pag. | Recall pag. | Hit pag. | "
                "Citacao | Itens | Falso positivo | P95 | LLM | Gate |"
            ),
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for engine in report.engines:
        metrics = engine.metrics
        lines.append(
            f"| `{engine.engine}` | {metrics.cases_count} | "
            f"{_percent(metrics.label_accuracy)} | "
            f"{_percent(metrics.page_precision)} | "
            f"{_percent(metrics.page_recall)} | "
            f"{_percent(metrics.page_hit_rate)} | "
            f"{_percent(metrics.citation_fidelity)} | "
            f"{_percent(metrics.item_recall)} | "
            f"{_percent(metrics.false_positive_case_rate)} | "
            f"{metrics.p95_latency_ms if metrics.p95_latency_ms is not None else '-'} | "
            f"{metrics.total_llm_calls} | `{engine.gate_status}` |"
        )
    for engine in report.engines:
        lines.extend(["", f"## {engine.engine}", ""])
        if engine.failed_checks:
            lines.append("Falhas do gate: " + "; ".join(engine.failed_checks))
            lines.append("")
        lines.extend(
            [
                (
                    "| Caso | Revisao | Rotulo | Recall pag. | Hit pag. | "
                    "Citacao | Itens | Acerto abstencao | Erro |"
                ),
                "|---|---|---:|---:|---:|---:|---:|---:|---|",
            ]
        )
        for case in engine.cases:
            lines.append(
                f"| `{case.case_id}` | `{case.review_status}` | "
                f"{_boolean(case.label_correct)} | "
                f"{_percent(case.page_recall)} | "
                f"{_boolean(case.page_hit)} | "
                f"{_percent(case.citation_fidelity)} | "
                f"{_percent(case.item_recall)} | "
                f"{_boolean(case.abstention_correct)} | {case.error or ''} |"
            )
        detailed_cases = [case for case in engine.cases if case.response]
        if detailed_cases:
            lines.extend(["", "### Respostas observadas", ""])
        for case in detailed_cases:
            lines.extend(
                [
                    f"#### {case.case_id}",
                    "",
                    f"Modelo: `{case.model or 'desconhecido'}`",
                    "",
                    f"Fallback: `{_boolean(case.fallback_used)}`",
                    "",
                    f"Paginas recuperadas: `{_pages(case.source_pages)}`",
                    "",
                    f"Paginas citadas: `{_pages(case.cited_pages)}`",
                    "",
                    case.response or "",
                    "",
                ]
            )
            if case.sources:
                lines.extend(["Fontes recuperadas:", ""])
                lines.extend(
                    f"- Pagina {source.page}, chunk {source.chunk_index}: "
                    f"{_excerpt(source.text)}"
                    for source in case.sources
                )
                lines.append("")
    return "\n".join(lines) + "\n"


def _score_case(
    case: IntegratedBenchmarkCase,
    observation: CaseObservation | None,
) -> IntegratedCaseResult:
    if observation is None:
        observation = CaseObservation(
            case_id=case.id,
            label=None,
            source_pages=None,
            cited_pages=None,
            items=None,
            abstained=None,
            latency_ms=None,
            llm_calls=0,
            prompt_tokens=None,
            completion_tokens=None,
            estimated_cost_usd=None,
            error="observacao ausente",
        )
    expected = case.expected
    source_pages = set(observation.source_pages or ())
    cited_pages = set(observation.cited_pages or ())
    expected_pages = set(expected.relevant_pages or ())
    response_expectations = tuple(expected.required_items or ()) + tuple(
        expected.forbidden_items or ()
    )
    response_items = (
        {
            item
            for item in response_expectations
            if text_contains_expected_item(observation.response or "", item)
        }
        if observation.response
        else set()
    )
    observed_item_values = set(observation.items or ()).union(response_items)
    observed_items = {_normalized(item) for item in observed_item_values}
    required_items = {_normalized(item) for item in expected.required_items or ()}
    forbidden_items = {_normalized(item) for item in expected.forbidden_items or ()}
    unexpected = tuple(sorted(observed_items.intersection(forbidden_items)))
    return IntegratedCaseResult(
        case_id=case.id,
        engine=case.engine,
        split=case.split,
        provenance=case.provenance,
        review_status=case.review_status,
        eligible_for_gate=case.eligible_for_gate,
        label_correct=(
            observation.label == expected.label if expected.label is not None else None
        ),
        page_precision=(
            _set_precision(source_pages, expected_pages)
            if expected.relevant_pages is not None and observation.source_pages is not None
            else None
        ),
        page_recall=(
            _set_recall(source_pages, expected_pages)
            if expected.relevant_pages is not None and observation.source_pages is not None
            else None
        ),
        page_hit=(
            bool(source_pages.intersection(expected_pages))
            if expected.relevant_pages is not None and observation.source_pages is not None
            else None
        ),
        citation_fidelity=(
            _set_precision(cited_pages, source_pages)
            if observation.cited_pages is not None and observation.source_pages is not None
            else None
        ),
        item_recall=(
            _set_recall(observed_items, required_items)
            if expected.required_items is not None and observation.items is not None
            else None
        ),
        false_positive=(bool(unexpected) if expected.forbidden_items is not None else None),
        unexpected_items=unexpected,
        abstention_correct=(
            observation.abstained == expected.should_abstain
            if expected.should_abstain is not None and observation.abstained is not None
            else None
        ),
        latency_ms=observation.latency_ms,
        llm_calls=observation.llm_calls,
        prompt_tokens=observation.prompt_tokens,
        completion_tokens=observation.completion_tokens,
        estimated_cost_usd=observation.estimated_cost_usd,
        error=observation.error,
        model=observation.model,
        fallback_used=observation.fallback_used,
        response=observation.response,
        source_pages=tuple(observation.source_pages or ()),
        cited_pages=tuple(observation.cited_pages or ()),
        observed_items=tuple(sorted(observed_item_values)),
        sources=observation.sources,
    )


def _summarize_engine(
    engine: str,
    results: tuple[IntegratedCaseResult, ...],
    suite: IntegratedBenchmarkSuite,
) -> EngineBenchmarkResult:
    engine_cases = tuple(item for item in results if item.engine == engine)
    eligible = tuple(item for item in engine_cases if item.eligible_for_gate)
    metrics = _metrics(engine_cases)
    gate_metrics = _metrics(eligible) if eligible else None
    if gate_metrics is None:
        gate_status = "not_eligible"
        failed_checks: tuple[str, ...] = ()
    else:
        gate = _merge_gate(suite.default_gate, suite.engine_gates.get(engine))
        failed_checks = tuple(_gate_failures(gate, gate_metrics))
        gate_status = "failed" if failed_checks else "passed"
    return EngineBenchmarkResult(
        engine=engine,
        metrics=metrics,
        gate_metrics=gate_metrics,
        gate_status=gate_status,
        failed_checks=failed_checks,
        cases=engine_cases,
    )


def _metrics(cases: tuple[IntegratedCaseResult, ...]) -> QualityMetrics:
    latencies = [item.latency_ms for item in cases if item.latency_ms is not None]
    costs = [item.estimated_cost_usd for item in cases if item.estimated_cost_usd is not None]
    prompt_tokens = [item.prompt_tokens for item in cases if item.prompt_tokens is not None]
    completion_tokens = [
        item.completion_tokens for item in cases if item.completion_tokens is not None
    ]
    return QualityMetrics(
        cases_count=len(cases),
        label_accuracy=_average_bools(item.label_correct for item in cases),
        page_precision=_average_optional(item.page_precision for item in cases),
        page_recall=_average_optional(item.page_recall for item in cases),
        page_hit_rate=_average_bools(item.page_hit for item in cases),
        citation_fidelity=_average_optional(item.citation_fidelity for item in cases),
        item_recall=_average_optional(item.item_recall for item in cases),
        abstention_accuracy=_average_bools(item.abstention_correct for item in cases),
        false_positive_case_rate=_average_bools(item.false_positive for item in cases),
        error_rate=_ratio(sum(item.error is not None for item in cases), len(cases)),
        p50_latency_ms=_percentile(latencies, 0.50),
        p95_latency_ms=_percentile(latencies, 0.95),
        total_llm_calls=sum(item.llm_calls for item in cases),
        average_llm_calls=round(
            sum(item.llm_calls for item in cases) / len(cases), 4
        ),
        prompt_tokens=sum(prompt_tokens) if prompt_tokens else None,
        completion_tokens=sum(completion_tokens) if completion_tokens else None,
        estimated_cost_usd=round(sum(costs), 8) if costs else None,
    )


def _gate_failures(gate: QualityGate, metrics: QualityMetrics) -> list[str]:
    failures: list[str] = []
    minimums = {
        "label_accuracy": gate.min_label_accuracy,
        "page_precision": gate.min_page_precision,
        "page_recall": gate.min_page_recall,
        "page_hit_rate": gate.min_page_hit_rate,
        "citation_fidelity": gate.min_citation_fidelity,
        "item_recall": gate.min_item_recall,
        "abstention_accuracy": gate.min_abstention_accuracy,
    }
    maximums = {
        "false_positive_case_rate": gate.max_false_positive_case_rate,
        "error_rate": gate.max_error_rate,
        "p95_latency_ms": gate.max_p95_latency_ms,
        "average_llm_calls": gate.max_average_llm_calls,
    }
    for name, threshold in minimums.items():
        if threshold is None:
            continue
        value = getattr(metrics, name)
        if value is None:
            failures.append(f"{name} sem casos aplicaveis")
        elif value < threshold:
            failures.append(f"{name}={value:.4f} abaixo de {threshold:.4f}")
    for name, threshold in maximums.items():
        if threshold is None:
            continue
        value = getattr(metrics, name)
        if value is None:
            failures.append(f"{name} sem casos aplicaveis")
        elif value > threshold:
            failures.append(f"{name}={value:.4f} acima de {threshold:.4f}")
    return failures


def _merge_gate(default: QualityGate, override: QualityGate | None) -> QualityGate:
    if override is None:
        return default
    return QualityGate(
        **{
            name: getattr(override, name)
            if getattr(override, name) is not None
            else getattr(default, name)
            for name in QualityGate.__dataclass_fields__
        }
    )


def _case_from_dict(value: object) -> IntegratedBenchmarkCase:
    item = _require_mapping(value, "caso")
    split = _require_text(item, "split")
    provenance = _require_text(item, "provenance")
    review_status = _require_text(item, "review_status")
    if split not in VALID_SPLITS:
        raise ValueError(f"Split invalido no caso: {split}")
    if provenance not in VALID_PROVENANCE:
        raise ValueError(f"Proveniencia invalida no caso: {provenance}")
    if review_status not in VALID_REVIEW_STATUSES:
        raise ValueError(f"Status de revisao invalido no caso: {review_status}")
    return IntegratedBenchmarkCase(
        id=_require_text(item, "id"),
        engine=_require_text(item, "engine"),
        split=split,
        provenance=provenance,
        review_status=review_status,
        description=_optional_text(item.get("description")),
        tags=tuple(_string_list(item.get("tags", []), "tags")),
        source=_source_from_dict(item.get("source")),
        expected=_expectation_from_dict(_require_mapping(item.get("expected", {}), "expected")),
    )


def _expectation_from_dict(item: dict[str, Any]) -> CaseExpectation:
    return CaseExpectation(
        label=_nullable_text(item.get("label")),
        relevant_pages=_optional_int_tuple(item, "relevant_pages"),
        required_items=_optional_text_tuple(item, "required_items"),
        forbidden_items=_optional_text_tuple(item, "forbidden_items"),
        should_abstain=_optional_bool(item, "should_abstain"),
    )


def _observation_from_dict(value: object) -> CaseObservation:
    item = _require_mapping(value, "observacao")
    return CaseObservation(
        case_id=_require_text(item, "case_id"),
        label=_nullable_text(item.get("label")),
        source_pages=_optional_int_tuple(item, "source_pages"),
        cited_pages=_optional_int_tuple(item, "cited_pages"),
        items=_optional_text_tuple(item, "items"),
        abstained=_optional_bool(item, "abstained"),
        latency_ms=_optional_non_negative_int(item, "latency_ms"),
        llm_calls=_non_negative_int(item.get("llm_calls", 0), "llm_calls"),
        prompt_tokens=_optional_non_negative_int(item, "prompt_tokens"),
        completion_tokens=_optional_non_negative_int(item, "completion_tokens"),
        estimated_cost_usd=_optional_non_negative_float(item, "estimated_cost_usd"),
        error=_nullable_text(item.get("error")),
        model=_nullable_text(item.get("model")),
        fallback_used=_optional_bool(item, "fallback_used"),
        response=_nullable_text(item.get("response")),
        sources=_observation_sources_from_dict(item.get("sources", [])),
    )


def _observation_sources_from_dict(value: object) -> tuple[ObservationSource, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("sources deve ser uma lista")
    sources = []
    for index, raw in enumerate(value):
        item = _require_mapping(raw, f"sources[{index}]")
        sources.append(
            ObservationSource(
                page=_positive_int(item.get("page"), f"sources[{index}].page"),
                chunk_index=_non_negative_int(
                    item.get("chunk_index"), f"sources[{index}].chunk_index"
                ),
                text=_require_text(item, "text"),
            )
        )
    return tuple(sources)


def _source_from_dict(value: object) -> BenchmarkSource | None:
    if value is None:
        return None
    item = _require_mapping(value, "source")
    return BenchmarkSource(
        reference_id=_require_text(item, "reference_id"),
        document=_require_text(item, "document"),
        title=_nullable_text(item.get("title")),
        url=_nullable_text(item.get("url")),
        sha256=_nullable_text(item.get("sha256")),
        text_sha256=_nullable_text(item.get("text_sha256")),
    )


def _gate_from_dict(item: dict[str, Any]) -> QualityGate:
    ratio_names = {
        "min_label_accuracy",
        "min_page_precision",
        "min_page_recall",
        "min_page_hit_rate",
        "min_citation_fidelity",
        "min_item_recall",
        "min_abstention_accuracy",
        "max_false_positive_case_rate",
        "max_error_rate",
    }
    values: dict[str, float | int | None] = {}
    for name in QualityGate.__dataclass_fields__:
        value = item.get(name)
        if value is None:
            values[name] = None
        elif name in ratio_names:
            values[name] = _ratio_value(value, name)
        elif name == "max_p95_latency_ms":
            values[name] = _non_negative_int(value, name)
        else:
            values[name] = _non_negative_float(value, name)
    unknown = set(item) - set(QualityGate.__dataclass_fields__)
    if unknown:
        raise ValueError("Campos de gate desconhecidos: " + ", ".join(sorted(unknown)))
    return QualityGate(**values)


def _load_mapping(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return _require_mapping(payload, "raiz")


def _write_json(payload: dict[str, object], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _require_schema(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version deve ser {SCHEMA_VERSION}")


def _require_mapping(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} deve ser um objeto")
    return value


def _require_list(payload: dict[str, Any], key: str) -> list[object]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} deve ser uma lista")
    return value


def _require_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} deve ser texto nao vazio")
    return value.strip()


def _optional_text(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("Campo opcional deve ser texto")
    return value.strip()


def _nullable_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Campo deve ser texto nao vazio ou nulo")
    return value.strip()


def _string_list(value: object, context: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(f"{context} deve ser uma lista de textos nao vazios")
    return [item.strip() for item in value]


def _optional_text_tuple(payload: dict[str, Any], key: str) -> tuple[str, ...] | None:
    if key not in payload or payload[key] is None:
        return None
    return tuple(_string_list(payload[key], key))


def _optional_int_tuple(payload: dict[str, Any], key: str) -> tuple[int, ...] | None:
    if key not in payload or payload[key] is None:
        return None
    value = payload[key]
    if not isinstance(value, list) or not all(
        isinstance(item, int) and not isinstance(item, bool) and item > 0 for item in value
    ):
        raise ValueError(f"{key} deve ser uma lista de paginas positivas")
    return tuple(dict.fromkeys(value))


def _optional_bool(payload: dict[str, Any], key: str) -> bool | None:
    if key not in payload or payload[key] is None:
        return None
    if not isinstance(payload[key], bool):
        raise ValueError(f"{key} deve ser booleano")
    return payload[key]


def _optional_non_negative_int(payload: dict[str, Any], key: str) -> int | None:
    if key not in payload or payload[key] is None:
        return None
    return _non_negative_int(payload[key], key)


def _optional_non_negative_float(payload: dict[str, Any], key: str) -> float | None:
    if key not in payload or payload[key] is None:
        return None
    return _non_negative_float(payload[key], key)


def _non_negative_int(value: object, context: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{context} deve ser inteiro nao negativo")
    return value


def _positive_int(value: object, context: str) -> int:
    result = _non_negative_int(value, context)
    if result == 0:
        raise ValueError(f"{context} deve ser maior que zero")
    return result


def _non_negative_float(value: object, context: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{context} deve ser numero nao negativo")
    return float(value)


def _ratio_value(value: object, context: str) -> float:
    ratio = _non_negative_float(value, context)
    if ratio > 1:
        raise ValueError(f"{context} deve estar entre zero e um")
    return ratio


def _ensure_unique(values, context: str) -> None:
    materialized = list(values)
    if len(materialized) != len(set(materialized)):
        raise ValueError(f"IDs duplicados em {context}")


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def text_contains_expected_item(text: str, expected_item: str) -> bool:
    normalized_text = _search_normalized(text)
    return any(
        normalized_alternative in normalized_text
        for alternative in expected_item.split(ITEM_ALTERNATIVE_SEPARATOR)
        if (normalized_alternative := _search_normalized(alternative))
    )


def _search_normalized(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return " ".join(re.findall(r"[a-z0-9]+", without_accents))


def _set_precision(observed: set[Any], expected: set[Any]) -> float:
    if not observed:
        return 1.0 if not expected else 0.0
    return round(len(observed.intersection(expected)) / len(observed), 4)


def _set_recall(observed: set[Any], expected: set[Any]) -> float:
    if not expected:
        return 1.0
    return round(len(observed.intersection(expected)) / len(expected), 4)


def _average_optional(values) -> float | None:
    selected = [value for value in values if value is not None]
    return round(mean(selected), 4) if selected else None


def _average_bools(values) -> float | None:
    selected = [value for value in values if value is not None]
    return _ratio(sum(selected), len(selected)) if selected else None


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _percentile(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _percent(value: float | None) -> str:
    return "-" if value is None else f"{value:.1%}"


def _boolean(value: bool | None) -> str:
    if value is None:
        return "-"
    return "sim" if value else "nao"


def _pages(pages: tuple[int, ...]) -> str:
    return ", ".join(str(page) for page in pages) or "nenhuma"


def _excerpt(text: str, limit: int = 500) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."
