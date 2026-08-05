from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from preparador_audiencia.integrated_benchmark import (
    BenchmarkSource,
    CaseExpectation,
    CaseObservation,
    IntegratedBenchmarkCase,
    IntegratedBenchmarkSuite,
    ObservationRun,
    QualityGate,
)
from preparador_audiencia.reference_suite import ReferenceCase, ReferenceSuite


def adapt_reference_benchmark(
    reference_suite: ReferenceSuite,
    report_payload: dict[str, Any],
    *,
    test_process_ids: set[str],
    run_id: str,
) -> tuple[IntegratedBenchmarkSuite, ObservationRun]:
    if report_payload.get("suite_id") != reference_suite.id:
        raise ValueError("O relatorio pertence a outra suite de referencia.")
    process_ids = {process.id for process in reference_suite.processes}
    unknown_test_ids = test_process_ids - process_ids
    if unknown_test_ids:
        raise ValueError(
            "Processos de teste desconhecidos: " + ", ".join(sorted(unknown_test_ids))
        )
    if not test_process_ids or test_process_ids == process_ids:
        raise ValueError("Os splits precisam ter ao menos um processo cada.")

    report_processes = _report_process_map(report_payload)
    missing_reports = process_ids - set(report_processes)
    extra_reports = set(report_processes) - process_ids
    if missing_reports or extra_reports:
        details = []
        if missing_reports:
            details.append("ausentes=" + ",".join(sorted(missing_reports)))
        if extra_reports:
            details.append("desconhecidos=" + ",".join(sorted(extra_reports)))
        raise ValueError("Processos divergentes no relatorio: " + "; ".join(details))

    cases: list[IntegratedBenchmarkCase] = []
    observations: list[CaseObservation] = []
    for process in reference_suite.processes:
        report_process = report_processes[process.id]
        report_cases = _report_case_map(report_process)
        expected_case_ids = {case.id for case in process.cases}
        if set(report_cases) != expected_case_ids:
            raise ValueError(f"Casos divergentes no processo {process.id}.")
        split = "test" if process.id in test_process_ids else "development"
        for reference_case in process.cases:
            report_case = report_cases[reference_case.id]
            _validate_case_identity(reference_case, report_case)
            case_id = f"{process.id}.{reference_case.id}"
            routed = _mapping(report_case.get("routed"), f"{case_id}.routed")
            pages = _positive_pages(routed.get("pages"), f"{case_id}.routed.pages")
            hit = routed.get("hit")
            if not isinstance(hit, bool):
                raise ValueError(f"{case_id}.routed.hit deve ser booleano.")
            cases.append(
                IntegratedBenchmarkCase(
                    id=case_id,
                    engine="recuperacao_hibrida",
                    split=split,
                    provenance="public_real",
                    review_status=_integrated_review_status(reference_case.review_status),
                    description=reference_case.pergunta,
                    tags=(process.domain, "stj", "recuperacao"),
                    source=BenchmarkSource(
                        reference_id=process.id,
                        document=process.document,
                        title=process.source,
                        url=process.source_url,
                        sha256=process.sha256,
                        text_sha256=process.text_sha256,
                    ),
                    expected=CaseExpectation(
                        label="fontes_relevantes_localizadas",
                        relevant_pages=tuple(reference_case.expected_pages),
                    ),
                )
            )
            observations.append(
                CaseObservation(
                    case_id=case_id,
                    label=(
                        "fontes_relevantes_localizadas"
                        if hit
                        else "fontes_relevantes_nao_localizadas"
                    ),
                    source_pages=tuple(dict.fromkeys(pages)),
                    cited_pages=None,
                    items=None,
                    abstained=None,
                    latency_ms=_non_negative_int(
                        routed.get("latency_ms"), f"{case_id}.routed.latency_ms"
                    ),
                    llm_calls=0,
                    prompt_tokens=None,
                    completion_tokens=None,
                    estimated_cost_usd=None,
                    error=None,
                )
            )

    embedding_model = str(report_payload.get("embedding_model", "desconhecido"))
    top_k = _non_negative_int(report_payload.get("top_k"), "top_k")
    suite = IntegratedBenchmarkSuite(
        id=f"{reference_suite.id}-integrado-v1",
        description=(
            "Benchmark publico convertido da suite de referencia. O split e feito "
            "por processo inteiro para evitar vazamento entre desenvolvimento e teste."
        ),
        cases=tuple(cases),
        default_gate=QualityGate(
            min_label_accuracy=0.9,
            min_page_recall=0.8,
            max_error_rate=0.0,
            max_p95_latency_ms=2000,
            max_average_llm_calls=0.0,
        ),
        engine_gates={},
    )
    observations_run = ObservationRun(
        suite_id=suite.id,
        run_id=run_id,
        producer=f"routing_benchmark:{embedding_model}:top_k={top_k}:routed",
        generated_at=datetime.now(UTC).isoformat(),
        observations=tuple(observations),
    )
    return suite, observations_run


def _report_process_map(report_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    values = report_payload.get("processes")
    if not isinstance(values, list):
        raise ValueError("processes deve ser uma lista no relatorio.")
    result = {}
    for value in values:
        item = _mapping(value, "processo do relatorio")
        reference_id = item.get("reference_id")
        if not isinstance(reference_id, str) or not reference_id:
            raise ValueError("reference_id invalido no relatorio.")
        if reference_id in result:
            raise ValueError(f"Processo duplicado no relatorio: {reference_id}")
        result[reference_id] = item
    return result


def _report_case_map(process: dict[str, Any]) -> dict[str, dict[str, Any]]:
    routing = _mapping(process.get("routing"), "routing")
    values = routing.get("cases")
    if not isinstance(values, list):
        raise ValueError("routing.cases deve ser uma lista.")
    result = {}
    for value in values:
        item = _mapping(value, "caso do relatorio")
        case_id = item.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError("case_id invalido no relatorio.")
        if case_id in result:
            raise ValueError(f"Caso duplicado no relatorio: {case_id}")
        result[case_id] = item
    return result


def _validate_case_identity(
    expected: ReferenceCase,
    observed: dict[str, Any],
) -> None:
    if observed.get("pergunta") != expected.pergunta:
        raise ValueError(f"Pergunta divergente no caso {expected.id}.")
    pages = _positive_pages(observed.get("expected_pages"), "expected_pages")
    if pages != expected.expected_pages:
        raise ValueError(f"Paginas esperadas divergentes no caso {expected.id}.")


def _integrated_review_status(status: str) -> str:
    if status == "approved":
        return "legal_approved"
    if status == "rejected":
        return "rejected"
    return "pending"


def _mapping(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} deve ser um objeto.")
    return value


def _positive_pages(value: object, context: str) -> list[int]:
    if not isinstance(value, list) or not all(
        isinstance(page, int) and not isinstance(page, bool) and page > 0
        for page in value
    ):
        raise ValueError(f"{context} deve conter paginas positivas.")
    return value


def _non_negative_int(value: object, context: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{context} deve ser inteiro nao negativo.")
    return value
