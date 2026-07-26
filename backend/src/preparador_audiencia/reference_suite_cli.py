from __future__ import annotations

import argparse
from pathlib import Path

from preparador_audiencia.environment import load_environment
from preparador_audiencia.reference_benchmark import (
    DEFAULT_INCLUDED_STATUSES,
    ensure_reference_document,
    run_reference_benchmark,
    write_reference_benchmark_report,
)
from preparador_audiencia.reference_suite import (
    REVIEW_STATUSES,
    load_reference_suite,
)
from preparador_audiencia.settings import embedding_provider_from_environment

DEFAULT_SUITE = "data/reference_suite_multidomain.json"
DEFAULT_SAMPLES_ROOT = "../samples/benchmark/multidominio"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Valida e executa a suite juridica multidominio."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validar")
    validate_parser.add_argument("--suite", default=DEFAULT_SUITE)

    run_parser = subparsers.add_parser("executar")
    run_parser.add_argument("--suite", default=DEFAULT_SUITE)
    run_parser.add_argument("--samples-root", default=DEFAULT_SAMPLES_ROOT)
    run_parser.add_argument("--download-missing", action="store_true")
    run_parser.add_argument("--top-k", type=int, default=5)
    run_parser.add_argument("--embedding")
    run_parser.add_argument(
        "--status",
        action="append",
        choices=sorted(REVIEW_STATUSES - {"rejected"}),
    )
    run_parser.add_argument(
        "--output",
        default="reports/benchmark-referencia-multidominio.json",
    )
    run_parser.add_argument("--env-file", default=".env")
    run_parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    suite = load_reference_suite(args.suite)
    if args.command == "validar":
        _print_suite_summary(suite)
        return

    load_environment(args.env_file)
    statuses = frozenset(args.status or DEFAULT_INCLUDED_STATUSES)
    if args.dry_run:
        _print_run_plan(
            suite,
            samples_root=args.samples_root,
            statuses=statuses,
            embedding=args.embedding or embedding_provider_from_environment(),
            top_k=args.top_k,
        )
        return

    report = run_reference_benchmark(
        suite,
        samples_root=args.samples_root,
        top_k=args.top_k,
        embedding_model=args.embedding,
        included_statuses=statuses,
        download_missing=args.download_missing,
    )
    output = Path(args.output)
    write_reference_benchmark_report(report, output)
    print(f"Relatorio JSON: {output}")
    print(f"Relatorio Markdown: {output.with_suffix('.md')}")
    print(f"Processos/casos: {report.total_processes}/{report.total_cases}")
    print(
        f"Hit rate bruto/triagem: {report.raw_hit_rate:.4f} / "
        f"{report.routed_hit_rate:.4f}"
    )
    print(f"MRR bruto/triagem: {report.raw_mrr:.4f} / {report.routed_mrr:.4f}")
    print(
        f"Melhorou/piorou/empatou: {report.improved_cases}/"
        f"{report.degraded_cases}/{report.tied_cases}"
    )


def _print_suite_summary(suite) -> None:
    cases = [case for process in suite.processes for case in process.cases]
    print(f"Suite valida: {suite.id}")
    print(f"Processos: {len(suite.processes)}")
    print(f"Casos: {len(cases)}")
    for status in sorted(REVIEW_STATUSES):
        count = sum(case.review_status == status for case in cases)
        print(f"{status}: {count}")


def _print_run_plan(
    suite,
    *,
    samples_root: str,
    statuses: frozenset[str],
    embedding: str,
    top_k: int,
) -> None:
    selected = [
        case
        for process in suite.processes
        for case in process.cases
        if case.review_status in statuses
    ]
    print("Plano da suite juridica multidominio")
    print(f"Suite: {suite.id}")
    print(f"Processos: {len(suite.processes)}")
    print(f"Casos selecionados: {len(selected)}")
    print(f"Status: {', '.join(sorted(statuses))}")
    print(f"Recuperador: {embedding}")
    print(f"Top K: {top_k}")
    for process in suite.processes:
        try:
            path = ensure_reference_document(process, samples_root)
            state = f"disponivel em {path}"
        except (FileNotFoundError, ValueError) as exc:
            state = str(exc)
        print(f"{process.id}: {state}")
    print("Nenhuma ingestao, indexacao ou chamada de LLM foi feita.")


if __name__ == "__main__":
    main()
