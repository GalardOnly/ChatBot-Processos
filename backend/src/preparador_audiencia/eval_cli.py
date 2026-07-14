from __future__ import annotations

import argparse
from pathlib import Path

from preparador_audiencia.environment import load_environment
from preparador_audiencia.evaluation import (
    load_evaluation_cases,
    run_poc_model_evaluation,
    write_report_files,
)

DEFAULT_MAX_LLM_CALLS = 4


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Avalia modelos de embedding e LLM para a PoC do Preparador de Audiencia."
    )
    parser.add_argument("--processo-id", required=True)
    parser.add_argument("--cases", required=True, help="Arquivo JSON com perguntas de avaliacao.")
    parser.add_argument(
        "--embedding",
        action="append",
        default=[],
        help="Recuperador. Padrao: legal-ensemble. Tambem aceita bertikal, jurisbert etc.",
    )
    parser.add_argument(
        "--llm-model",
        action="append",
        default=[],
        help=(
            "Modelo no formato provedor:modelo. "
            "Padrao da PoC: gemini:gemini-flash-latest; fallback: groq:llama-3.1-8b-instant."
        ),
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output", default="reports/poc-modelos.json")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--max-llm-calls", type=int, default=DEFAULT_MAX_LLM_CALLS)
    parser.add_argument("--allow-paid-over-limit", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_environment(args.env_file)
    embedding_specs = args.embedding or ["legal-ensemble"]
    cases = load_evaluation_cases(args.cases)
    planned_llm_calls = estimate_llm_calls(cases_count=len(cases), llm_models=args.llm_model)
    if args.dry_run:
        print_plan(embedding_specs, args.llm_model, planned_llm_calls, args.max_llm_calls)
        return
    validate_llm_budget(
        planned_calls=planned_llm_calls,
        max_calls=args.max_llm_calls,
        allow_over_limit=args.allow_paid_over_limit,
        parser=parser,
    )
    report = run_poc_model_evaluation(
        processo_id=args.processo_id,
        cases=cases,
        embedding_specs=embedding_specs,
        llm_models=args.llm_model,
        top_k=args.top_k,
    )
    write_report_files(report, Path(args.output))

    print(f"Relatorio JSON: {args.output}")
    print(f"Relatorio Markdown: {Path(args.output).with_suffix('.md')}")
    print(f"Melhor embedding: {report.best_embedding_model or 'nao definido'}")
    print(f"Melhor LLM: {report.best_llm_model or 'nao avaliado'}")


def estimate_llm_calls(cases_count: int, llm_models: list[str]) -> int:
    return cases_count * len(llm_models)


def validate_llm_budget(
    planned_calls: int,
    max_calls: int,
    allow_over_limit: bool,
    parser: argparse.ArgumentParser,
) -> None:
    if planned_calls <= max_calls or allow_over_limit:
        return
    parser.error(
        f"avaliacao faria {planned_calls} chamadas de LLM, acima do limite {max_calls}. "
        "Reduza casos/modelos, aumente --max-llm-calls ou use --allow-paid-over-limit."
    )


def print_plan(
    embedding_specs: list[str],
    llm_models: list[str],
    planned_llm_calls: int,
    max_llm_calls: int,
) -> None:
    print("Plano da avaliacao PoC")
    print(f"Recuperadores: {', '.join(embedding_specs)}")
    print(f"LLMs: {', '.join(llm_models) if llm_models else 'nenhum'}")
    print(f"Chamadas LLM planejadas: {planned_llm_calls}")
    print(f"Limite atual: {max_llm_calls}")
    print("Nenhuma chamada externa foi feita por causa do --dry-run.")


if __name__ == "__main__":
    main()
