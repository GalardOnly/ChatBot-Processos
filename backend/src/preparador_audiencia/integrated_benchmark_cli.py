from __future__ import annotations

import argparse
from pathlib import Path

from preparador_audiencia.integrated_benchmark import (
    VALID_SPLITS,
    load_integrated_benchmark_suite,
    load_observation_run,
    run_integrated_benchmark,
    write_integrated_benchmark_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Consolida a qualidade dos motores em um unico relatorio."
    )
    parser.add_argument(
        "--suite",
        default="data/integrated_benchmark_v01.json",
        help="Gabarito versionado do benchmark.",
    )
    parser.add_argument(
        "--observations",
        default="data/integrated_benchmark_observations_calibration.json",
        help="Resultados observados produzidos pelos motores.",
    )
    parser.add_argument(
        "--split",
        choices=sorted(VALID_SPLITS),
        default="development",
        help="Development serve para ajuste; test e reservado para avaliacao.",
    )
    parser.add_argument("--case-ids", nargs="+")
    parser.add_argument("--output", default="reports/benchmark-integrado.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    suite = load_integrated_benchmark_suite(args.suite)
    observations = load_observation_run(args.observations)
    selected_ids = set(args.case_ids) if args.case_ids else None
    report = run_integrated_benchmark(
        suite,
        observations,
        split=args.split,
        case_ids=selected_ids,
    )
    if args.dry_run:
        _print_plan(report, args.output)
        return

    write_integrated_benchmark_report(report, Path(args.output))
    print(f"Relatorio JSON: {args.output}")
    print(f"Relatorio Markdown: {Path(args.output).with_suffix('.md')}")
    print(f"Casos avaliados: {report.cases_count}")
    print(f"Casos com revisao juridica aprovada: {report.legal_approved_cases}")
    print(f"Gate geral: {report.gate_status}")
    print("Nenhuma chamada externa foi feita pelo consolidador.")


def _print_plan(report, output: str) -> None:
    print("Plano do benchmark integrado")
    print(f"Suite: {report.suite_id}")
    print(f"Split: {report.split}")
    print(f"Casos: {report.cases_count}")
    print(f"Motores: {len(report.engines)}")
    print(f"Saida prevista: {output}")
    print("Nenhuma chamada externa foi feita por causa do --dry-run.")


if __name__ == "__main__":
    main()
