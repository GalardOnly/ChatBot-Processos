from __future__ import annotations

import argparse
from pathlib import Path

from preparador_audiencia.environment import load_environment
from preparador_audiencia.eval_cli import validate_llm_budget
from preparador_audiencia.nullity_benchmark import (
    NullityBenchmarkSuite,
    estimate_nullity_llm_calls,
    load_nullity_benchmark_suite,
    run_nullity_benchmark,
    write_nullity_benchmark_report,
)
from preparador_audiencia.settings import (
    fallback_llm_from_environment,
    primary_llm_from_environment,
)

DEFAULT_MAX_LLM_CALLS = 12


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compara modelos na analise controlada de nulidade do reconhecimento."
        )
    )
    parser.add_argument(
        "--cases",
        default="data/nullity_benchmark_recognition.json",
        help="Arquivo JSON com casos e resultados esperados.",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        help="Modelos no formato provedor:modelo. O padrao usa Gemini e Groq da .env.",
    )
    parser.add_argument("--limit-cases", type=int)
    parser.add_argument(
        "--case-ids",
        nargs="+",
        help="Executa somente os casos informados, preservando a ordem da suite.",
    )
    parser.add_argument(
        "--output",
        default="reports/benchmark-nulidades-reconhecimento.json",
    )
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--delay-seconds", type=float, default=0.5)
    parser.add_argument("--max-llm-calls", type=int, default=DEFAULT_MAX_LLM_CALLS)
    parser.add_argument("--allow-paid-over-limit", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_environment(args.env_file)
    suite = load_nullity_benchmark_suite(args.cases)
    if args.case_ids:
        suite = _select_cases(suite, args.case_ids, parser)
    if args.limit_cases is not None:
        suite = _limit_suite(suite, args.limit_cases)
    models = _unique_models(
        args.models
        or [
            primary_llm_from_environment(),
            fallback_llm_from_environment(),
        ]
    )
    planned_calls = estimate_nullity_llm_calls(len(suite.cases), len(models))

    if args.dry_run:
        _print_plan(suite, models, planned_calls, args.max_llm_calls)
        return

    validate_llm_budget(
        planned_calls=planned_calls,
        max_calls=args.max_llm_calls,
        allow_over_limit=args.allow_paid_over_limit,
        parser=parser,
    )
    report = run_nullity_benchmark(
        suite,
        models,
        delay_seconds=max(0.0, args.delay_seconds),
    )
    write_nullity_benchmark_report(report, Path(args.output))

    print(f"Relatorio JSON: {args.output}")
    print(f"Relatorio Markdown: {Path(args.output).with_suffix('.md')}")
    for result in report.models:
        print(
            f"{result.model}: conclusao {result.conclusion_accuracy:.1%}, "
            f"requisitos {result.requirement_accuracy:.1%}, "
            f"paginas {result.page_reference_accuracy:.1%}, "
            f"nota {result.average_weighted_score:.1f}, "
            f"gate {'aprovado' if result.gate_passed else 'reprovado'}"
        )


def _limit_suite(suite: NullityBenchmarkSuite, limit: int) -> NullityBenchmarkSuite:
    return NullityBenchmarkSuite(
        id=suite.id,
        description=suite.description,
        legal_review_status=suite.legal_review_status,
        cases=suite.cases[: max(0, limit)],
    )


def _select_cases(
    suite: NullityBenchmarkSuite,
    case_ids: list[str],
    parser: argparse.ArgumentParser,
) -> NullityBenchmarkSuite:
    wanted = set(case_ids)
    selected = tuple(case for case in suite.cases if case.id in wanted)
    missing = wanted - {case.id for case in selected}
    if missing:
        parser.error(f"Casos desconhecidos: {', '.join(sorted(missing))}")
    return NullityBenchmarkSuite(
        id=suite.id,
        description=suite.description,
        legal_review_status=suite.legal_review_status,
        cases=selected,
    )


def _unique_models(models: list[str]) -> list[str]:
    return list(dict.fromkeys(model.strip() for model in models if model.strip()))


def _print_plan(
    suite: NullityBenchmarkSuite,
    models: list[str],
    planned_calls: int,
    max_calls: int,
) -> None:
    print("Plano do benchmark de nulidades")
    print(f"Suite: {suite.id}")
    print(f"Casos: {len(suite.cases)}")
    print(f"Modelos: {', '.join(models)}")
    print(f"Chamadas LLM planejadas no pior caso: {planned_calls}")
    print(f"Limite configurado: {max_calls}")
    print("Nenhuma chamada externa foi feita por causa do --dry-run.")


if __name__ == "__main__":
    main()
