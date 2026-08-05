from __future__ import annotations

import argparse
import json
from pathlib import Path

from preparador_audiencia.integrated_benchmark import (
    run_integrated_benchmark,
    write_integrated_benchmark_report,
    write_integrated_benchmark_suite,
    write_observation_run,
)
from preparador_audiencia.integrated_reference_adapter import (
    adapt_reference_benchmark,
)
from preparador_audiencia.reference_suite import load_reference_suite


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Converte um benchmark publico de referencia para o schema integrado."
    )
    parser.add_argument(
        "--reference-suite",
        default="data/reference_suite_multidomain.json",
    )
    parser.add_argument("--reference-report", required=True)
    parser.add_argument("--test-process", nargs="+", required=True)
    parser.add_argument("--run-id", default="referencia-publica-v1")
    parser.add_argument(
        "--suite-output",
        default="data/integrated_benchmark_stj_public_v01.json",
    )
    parser.add_argument(
        "--observations-output",
        default="data/integrated_observations_stj_public_v01.json",
    )
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    reference_suite = load_reference_suite(args.reference_suite)
    report_payload = json.loads(Path(args.reference_report).read_text(encoding="utf-8"))
    if not isinstance(report_payload, dict):
        parser.error("O relatorio de referencia deve ser um objeto JSON.")
    suite, observations = adapt_reference_benchmark(
        reference_suite,
        report_payload,
        test_process_ids=set(args.test_process),
        run_id=args.run_id,
    )
    development = run_integrated_benchmark(suite, observations, split="development")
    test = run_integrated_benchmark(suite, observations, split="test")

    _print_summary(development, test)
    if args.dry_run:
        print("Nenhum arquivo foi gravado e nenhuma chamada externa foi feita.")
        return

    write_integrated_benchmark_suite(suite, args.suite_output)
    write_observation_run(observations, args.observations_output)
    reports_dir = Path(args.reports_dir)
    write_integrated_benchmark_report(
        development,
        reports_dir / "benchmark-integrado-stj-development.json",
    )
    write_integrated_benchmark_report(
        test,
        reports_dir / "benchmark-integrado-stj-test.json",
    )
    print(f"Suite integrada: {args.suite_output}")
    print(f"Observacoes reais: {args.observations_output}")
    print(f"Relatorios: {reports_dir}")


def _print_summary(development, test) -> None:
    print("Conversao do benchmark publico")
    for report in (development, test):
        engine = report.engines[0]
        print(
            f"{report.split}: {report.cases_count} casos, "
            f"hit {engine.metrics.label_accuracy:.1%}, "
            f"recall de paginas {engine.metrics.page_recall:.1%}, "
            f"gate {report.gate_status}"
        )


if __name__ == "__main__":
    main()
