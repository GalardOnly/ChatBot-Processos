from __future__ import annotations

import argparse
import os

from preparador_audiencia.database import database_path_from_environment
from preparador_audiencia.environment import load_environment
from preparador_audiencia.integrated_benchmark import (
    run_integrated_benchmark,
    write_integrated_benchmark_report,
    write_integrated_benchmark_suite,
    write_observation_run,
)
from preparador_audiencia.integrated_chat_benchmark import (
    build_chat_reference_suite,
    create_database_snapshot,
    estimate_chat_llm_calls,
    run_chat_observations,
)
from preparador_audiencia.reference_suite import load_reference_suite
from preparador_audiencia.settings import (
    fallback_llm_from_environment,
    primary_llm_from_environment,
)

DEFAULT_MAX_LLM_CALLS = 6


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Avalia respostas reais do chat em fontes publicas."
    )
    parser.add_argument(
        "--reference-suite",
        default="data/reference_suite_multidomain.json",
    )
    parser.add_argument("--test-process", nargs="+", required=True)
    parser.add_argument("--process-map", nargs="+", required=True)
    parser.add_argument(
        "--split",
        choices=("development", "test"),
        default="development",
    )
    parser.add_argument("--allow-test", action="store_true")
    parser.add_argument("--case-ids", nargs="+")
    parser.add_argument("--limit-cases", type=int, default=3)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--primary")
    parser.add_argument("--fallback")
    parser.add_argument("--max-llm-calls", type=int, default=DEFAULT_MAX_LLM_CALLS)
    parser.add_argument("--run-id", default="chat-publico-development-v1")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument(
        "--database-snapshot",
        default="cache/benchmarks/chat-publico.sqlite3",
    )
    parser.add_argument(
        "--suite-output",
        default="data/integrated_benchmark_chat_stj_public_v01.json",
    )
    parser.add_argument(
        "--observations-output",
        default="reports/observations-chat-stj-development.json",
    )
    parser.add_argument(
        "--report-output",
        default="reports/benchmark-chat-stj-development.json",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.split == "test" and not args.allow_test:
        parser.error("O split de teste exige --allow-test.")
    if args.top_k <= 0:
        parser.error("--top-k deve ser maior que zero.")
    if args.limit_cases is not None and args.limit_cases <= 0:
        parser.error("--limit-cases deve ser maior que zero.")

    load_environment(args.env_file)
    reference_suite = load_reference_suite(args.reference_suite)
    suite = build_chat_reference_suite(
        reference_suite,
        test_process_ids=set(args.test_process),
    )
    selected_ids = _selected_case_ids(
        suite,
        split=args.split,
        requested_ids=set(args.case_ids) if args.case_ids else None,
        limit=args.limit_cases,
    )
    planned_calls = estimate_chat_llm_calls(len(selected_ids))
    if planned_calls > args.max_llm_calls:
        parser.error(
            f"A execucao pode usar {planned_calls} chamadas, acima do limite "
            f"de {args.max_llm_calls}."
        )
    primary = args.primary or primary_llm_from_environment()
    fallback = args.fallback or fallback_llm_from_environment()
    process_map = _parse_process_map(args.process_map, parser)
    _print_plan(args, selected_ids, primary, fallback, planned_calls)
    if args.dry_run:
        print("Nenhum banco foi copiado e nenhuma chamada externa foi feita.")
        return

    active_database = database_path_from_environment()
    snapshot = create_database_snapshot(active_database, args.database_snapshot)
    os.environ["PREPARADOR_DATABASE_PATH"] = str(snapshot)
    observations = run_chat_observations(
        suite,
        process_map=process_map,
        split=args.split,
        case_ids=selected_ids,
        top_k=args.top_k,
        primary_model=primary,
        fallback_model=fallback,
        max_llm_calls=args.max_llm_calls,
        run_id=args.run_id,
    )
    report = run_integrated_benchmark(
        suite,
        observations,
        split=args.split,
        case_ids=selected_ids,
    )
    write_integrated_benchmark_suite(suite, args.suite_output)
    write_observation_run(observations, args.observations_output)
    write_integrated_benchmark_report(report, args.report_output)
    print(f"Snapshot local: {snapshot}")
    print(f"Observacoes: {args.observations_output}")
    print(f"Relatorio: {args.report_output}")
    metrics = report.engines[0].metrics
    print(f"Hit de paginas: {_percent(metrics.page_hit_rate)}")
    print(f"Recall de paginas: {_percent(metrics.page_recall)}")
    print(f"Fidelidade das citacoes: {_percent(metrics.citation_fidelity)}")
    print(f"Cobertura de termos: {_percent(metrics.item_recall)}")
    print(f"Chamadas LLM realizadas: {metrics.total_llm_calls}")


def _selected_case_ids(suite, *, split: str, requested_ids, limit: int | None) -> set[str]:
    available = [case.id for case in suite.cases if case.split == split]
    if requested_ids is not None:
        missing = requested_ids - set(available)
        if missing:
            raise ValueError("Casos desconhecidos: " + ", ".join(sorted(missing)))
        selected = [case_id for case_id in available if case_id in requested_ids]
    else:
        selected = available
    if limit is not None:
        selected = selected[:limit]
    return set(selected)


def _parse_process_map(values: list[str], parser: argparse.ArgumentParser) -> dict[str, str]:
    result = {}
    for value in values:
        reference_id, separator, processo_id = value.partition("=")
        if not separator or not reference_id.strip() or not processo_id.strip():
            parser.error(f"Mapeamento invalido: {value}")
        result[reference_id.strip()] = processo_id.strip()
    return result


def _print_plan(args, case_ids, primary: str, fallback: str, planned_calls: int) -> None:
    print("Plano do benchmark publico do chat")
    print(f"Split: {args.split}")
    print(f"Casos: {len(case_ids)}")
    print(f"Top K: {args.top_k}")
    print(f"Principal: {primary}")
    print(f"Fallback: {fallback}")
    print(f"Chamadas planejadas no pior caso: {planned_calls}")
    print(f"Limite: {args.max_llm_calls}")


def _percent(value: float | None) -> str:
    return "-" if value is None else f"{value:.1%}"


if __name__ == "__main__":
    main()
