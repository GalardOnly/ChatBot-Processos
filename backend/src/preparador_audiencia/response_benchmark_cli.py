from __future__ import annotations

import argparse
from pathlib import Path

from preparador_audiencia.environment import load_environment
from preparador_audiencia.eval_cli import validate_llm_budget
from preparador_audiencia.evaluation import load_evaluation_cases
from preparador_audiencia.response_benchmark import (
    run_response_quality_benchmark,
    write_response_benchmark_report,
)
from preparador_audiencia.settings import (
    embedding_provider_from_environment,
    evaluator_llm_from_environment,
    fallback_llm_from_environment,
    primary_llm_from_environment,
)

DEFAULT_MAX_LLM_CALLS = 6


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Avalia respostas completas da PoC com recuperacao, geracao e avaliacao LLM."
    )
    parser.add_argument("--processo-id", required=True)
    parser.add_argument("--cases", required=True, help="Arquivo JSON com perguntas de avaliacao.")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--limit-cases", type=int, help="Limita a quantidade de casos da rodada.")
    parser.add_argument("--embedding", help="Recuperador usado antes de gerar as respostas.")
    parser.add_argument("--generator", help="Modelo gerador principal no formato provedor:modelo.")
    parser.add_argument("--fallback", help="Modelo fallback no formato provedor:modelo.")
    parser.add_argument("--evaluator", help="Modelo avaliador no formato provedor:modelo.")
    parser.add_argument("--output", default="reports/benchmark-respostas.json")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--max-llm-calls", type=int, default=DEFAULT_MAX_LLM_CALLS)
    parser.add_argument("--allow-paid-over-limit", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_environment(args.env_file)
    cases = load_evaluation_cases(args.cases)
    if args.limit_cases is not None:
        cases = cases[: max(0, args.limit_cases)]
    generator = args.generator or primary_llm_from_environment()
    fallback = args.fallback or fallback_llm_from_environment()
    evaluator = args.evaluator or evaluator_llm_from_environment()
    embedding = args.embedding or embedding_provider_from_environment()
    planned_calls = estimate_response_llm_calls(len(cases))

    if args.dry_run:
        print_plan(
            generator=generator,
            fallback=fallback,
            evaluator=evaluator,
            embedding=embedding,
            cases_count=len(cases),
            planned_calls=planned_calls,
            max_llm_calls=args.max_llm_calls,
            top_k=args.top_k,
        )
        return

    validate_llm_budget(
        planned_calls=planned_calls,
        max_calls=args.max_llm_calls,
        allow_over_limit=args.allow_paid_over_limit,
        parser=parser,
    )
    report = run_response_quality_benchmark(
        processo_id=args.processo_id,
        cases=cases,
        top_k=args.top_k,
        generator_model=generator,
        fallback_model=fallback,
        evaluator_model=evaluator,
        embedding_model=embedding,
    )
    write_response_benchmark_report(report, Path(args.output))

    print(f"Relatorio JSON: {args.output}")
    print(f"Relatorio Markdown: {Path(args.output).with_suffix('.md')}")
    print(f"Fidelidade media: {report.average_fidelidade_fontes:.2f}/5")
    print(f"Completude media: {report.average_completude_juridica:.2f}/5")
    print(f"Utilidade media: {report.average_utilidade_audiencia:.2f}/5")
    print(f"Casos com risco alto: {report.high_risk_count}")


def estimate_response_llm_calls(cases_count: int) -> int:
    return cases_count * 3


def print_plan(
    *,
    generator: str,
    fallback: str,
    evaluator: str,
    embedding: str,
    cases_count: int,
    planned_calls: int,
    max_llm_calls: int,
    top_k: int,
) -> None:
    print("Plano do benchmark de respostas")
    print(f"Casos: {cases_count}")
    print(f"Top K: {top_k}")
    print(f"Gerador principal: {generator}")
    print(f"Fallback: {fallback}")
    print(f"Avaliador: {evaluator}")
    print(f"Recuperador: {embedding}")
    print(f"Chamadas LLM planejadas no pior caso: {planned_calls}")
    print(f"Limite atual: {max_llm_calls}")
    print("Nenhuma chamada externa foi feita por causa do --dry-run.")


if __name__ == "__main__":
    main()
