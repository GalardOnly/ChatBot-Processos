from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from preparador_audiencia.chat import answer_process_question
from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.integrated_benchmark import (
    BenchmarkSource,
    CaseExpectation,
    CaseObservation,
    IntegratedBenchmarkCase,
    IntegratedBenchmarkSuite,
    ObservationRun,
    ObservationSource,
    QualityGate,
    text_contains_expected_item,
)
from preparador_audiencia.quality_signals import extract_cited_pages
from preparador_audiencia.reference_suite import ReferenceSuite
from preparador_audiencia.repositories import ProcessoRepository

_MOJIBAKE_MARKERS = ("\u00c3", "\u00c2", "\u00e2")


class _DiscardMessages:
    def add(self, *_args, **_kwargs) -> None:
        return None


def build_chat_reference_suite(
    reference_suite: ReferenceSuite,
    *,
    test_process_ids: set[str],
) -> IntegratedBenchmarkSuite:
    process_ids = {process.id for process in reference_suite.processes}
    unknown = test_process_ids - process_ids
    if unknown:
        raise ValueError("Processos de teste desconhecidos: " + ", ".join(sorted(unknown)))
    if not test_process_ids or test_process_ids == process_ids:
        raise ValueError("Os splits precisam ter ao menos um processo cada.")

    cases = []
    for process in reference_suite.processes:
        split = "test" if process.id in test_process_ids else "development"
        for reference_case in process.cases:
            cases.append(
                IntegratedBenchmarkCase(
                    id=f"chat.{process.id}.{reference_case.id}",
                    engine="chat",
                    split=split,
                    provenance="public_real",
                    review_status=_review_status(reference_case.review_status),
                    description=reference_case.pergunta,
                    tags=(process.domain, "stj", "chat"),
                    source=BenchmarkSource(
                        reference_id=process.id,
                        document=process.document,
                        title=process.source,
                        url=process.source_url,
                        sha256=process.sha256,
                        text_sha256=process.text_sha256,
                    ),
                    expected=CaseExpectation(
                        label="resposta_gerada",
                        relevant_pages=tuple(
                            reference_case.response_relevant_pages
                            or reference_case.expected_pages
                        ),
                        required_items=tuple(
                            _repair_mojibake(term)
                            for term in (
                                reference_case.response_expected_terms
                                or reference_case.expected_terms
                            )
                        ),
                        should_abstain=False,
                    ),
                )
            )
    return IntegratedBenchmarkSuite(
        id=f"{reference_suite.id}-chat-integrado-v1",
        description=(
            "Benchmark publico do chat. Os termos esperados sao usados somente "
            "depois da geracao e nunca entram no prompt do modelo."
        ),
        cases=tuple(cases),
        default_gate=QualityGate(
            min_label_accuracy=0.9,
            min_page_hit_rate=1.0,
            min_citation_fidelity=1.0,
            min_item_recall=0.8,
            min_abstention_accuracy=1.0,
            max_error_rate=0.0,
            max_p95_latency_ms=20_000,
            max_average_llm_calls=1.2,
        ),
        engine_gates={},
    )


def run_chat_observations(
    suite: IntegratedBenchmarkSuite,
    *,
    process_map: dict[str, str],
    split: str,
    case_ids: set[str] | None,
    top_k: int,
    primary_model: str,
    fallback_model: str,
    max_llm_calls: int,
    run_id: str,
) -> ObservationRun:
    selected = [
        case
        for case in suite.cases
        if case.split == split and (case_ids is None or case.id in case_ids)
    ]
    if case_ids is not None:
        missing = case_ids - {case.id for case in selected}
        if missing:
            raise ValueError("Casos nao encontrados no split: " + ", ".join(sorted(missing)))
    if not selected:
        raise ValueError(f"Nenhum caso selecionado no split {split}.")
    planned_calls = estimate_chat_llm_calls(len(selected))
    if planned_calls > max_llm_calls:
        raise ValueError(
            f"A execucao pode usar {planned_calls} chamadas, acima do limite "
            f"de {max_llm_calls}."
        )
    required_references = {
        case.source.reference_id for case in selected if case.source is not None
    }
    _validate_process_map(required_references, process_map)

    observations = tuple(
        _run_case(
            case,
            process_map[case.source.reference_id],
            top_k=top_k,
            primary_model=primary_model,
            fallback_model=fallback_model,
        )
        for case in selected
        if case.source is not None
    )
    return ObservationRun(
        suite_id=suite.id,
        run_id=run_id,
        producer=f"chat:{primary_model}:fallback={fallback_model}:top_k={top_k}",
        generated_at=datetime.now(UTC).isoformat(),
        observations=observations,
    )


def estimate_chat_llm_calls(cases_count: int) -> int:
    return max(0, cases_count) * 2


def create_database_snapshot(source_path: str | Path, target_path: str | Path) -> Path:
    source = Path(source_path).resolve()
    target = Path(target_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Banco de origem nao encontrado: {source}")
    if source == target:
        raise ValueError("O snapshot precisa ser diferente do banco ativo.")
    target.parent.mkdir(parents=True, exist_ok=True)
    source_connection = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    target_connection = sqlite3.connect(target)
    try:
        source_connection.backup(target_connection)
    finally:
        target_connection.close()
        source_connection.close()
    return target


def _run_case(
    case: IntegratedBenchmarkCase,
    processo_id: str,
    *,
    top_k: int,
    primary_model: str,
    fallback_model: str,
) -> CaseObservation:
    started = perf_counter()
    try:
        result = answer_process_question(
            processo_id=processo_id,
            pergunta=case.description,
            messages=_DiscardMessages(),
            top_k=top_k,
            primary_model=primary_model,
            fallback_model=fallback_model,
            evaluate_quality=False,
        )
    except Exception as exc:
        return CaseObservation(
            case_id=case.id,
            label="resposta_nao_gerada",
            source_pages=None,
            cited_pages=None,
            items=None,
            abstained=True,
            latency_ms=_elapsed_ms(started),
            llm_calls=2,
            prompt_tokens=None,
            completion_tokens=None,
            estimated_cost_usd=None,
            error=str(exc),
        )

    response = result.resposta.strip()
    generated = bool(response and result.modelo and result.modelo != "sistema")
    source_pages = tuple(sorted({source.page_number for source in result.fontes}))
    cited_pages = tuple(extract_cited_pages(response))
    expected_terms = case.expected.required_items or ()
    matched_items = tuple(
        term for term in expected_terms if _contains_term(response, term)
    )
    if result.modelo == "sistema":
        llm_calls = 0
    else:
        llm_calls = 2 if result.fallback_usado else 1
    return CaseObservation(
        case_id=case.id,
        label="resposta_gerada" if generated else "resposta_nao_gerada",
        source_pages=source_pages,
        cited_pages=cited_pages,
        items=matched_items,
        abstained=not generated,
        latency_ms=_elapsed_ms(started),
        llm_calls=llm_calls,
        prompt_tokens=None,
        completion_tokens=None,
        estimated_cost_usd=None,
        error=result.erro,
        model=result.modelo,
        fallback_used=result.fallback_usado,
        response=response or None,
        sources=tuple(
            ObservationSource(
                page=source.page_number,
                chunk_index=source.chunk_index,
                text=source.text,
            )
            for source in result.fontes
        ),
    )


def _validate_process_map(
    required_references: set[str],
    process_map: dict[str, str],
) -> None:
    missing = required_references - set(process_map)
    if missing:
        raise ValueError("Mapeamento ausente para: " + ", ".join(sorted(missing)))
    connection = connect_database()
    initialize_database(connection)
    try:
        repository = ProcessoRepository(connection)
        for reference_id in required_references:
            processo_id = process_map[reference_id]
            record = repository.get(processo_id)
            if record is None:
                raise ValueError(f"Processo local nao encontrado: {processo_id}")
            if record.status != "concluido":
                raise ValueError(
                    f"Processo local {processo_id} esta com status {record.status}."
                )
    finally:
        connection.close()


def _review_status(status: str) -> str:
    if status == "approved":
        return "legal_approved"
    if status == "rejected":
        return "rejected"
    return "pending"


def _repair_mojibake(value: str) -> str:
    repaired = value
    for _ in range(2):
        if not any(marker in repaired for marker in _MOJIBAKE_MARKERS):
            break
        try:
            candidate = repaired.encode("latin-1").decode("utf-8")
        except UnicodeError:
            break
        if candidate == repaired:
            break
        repaired = candidate
    return repaired


def _contains_term(text: str, term: str) -> bool:
    return text_contains_expected_item(text, term)


def _elapsed_ms(started: float) -> int:
    return round((perf_counter() - started) * 1000)
