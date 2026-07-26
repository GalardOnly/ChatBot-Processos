from __future__ import annotations

import argparse
from pathlib import Path

from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.environment import load_environment
from preparador_audiencia.eval_cli import validate_llm_budget
from preparador_audiencia.evaluation import load_evaluation_cases
from preparador_audiencia.repositories import ChunkRepository
from preparador_audiencia.routing_benchmark import (
    generate_cases_from_chunks,
    run_routing_benchmark,
    write_routing_benchmark_report,
)
from preparador_audiencia.settings import (
    embedding_provider_from_environment,
    fallback_llm_from_environment,
    primary_llm_from_environment,
)

DEFAULT_MAX_LLM_CALLS = 4


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compara perguntas brutas com a triagem interna do chat."
    )
    parser.add_argument("--processo-id", required=True)
    parser.add_argument("--cases", help="JSON opcional com paginas e termos esperados.")
    parser.add_argument("--generate-cases", type=int, default=50)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--embedding")
    parser.add_argument("--llm-cases", type=int, default=0)
    parser.add_argument("--generator")
    parser.add_argument("--fallback")
    parser.add_argument("--output", default="reports/benchmark-roteamento.json")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--max-llm-calls", type=int, default=DEFAULT_MAX_LLM_CALLS)
    parser.add_argument("--allow-paid-over-limit", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_environment(args.env_file)
    cases = _load_or_generate_cases(
        processo_id=args.processo_id,
        cases_path=args.cases,
        generate_limit=max(0, args.generate_cases),
    )
    if not cases:
        parser.error("Nenhum caso de benchmark foi encontrado ou gerado.")
    llm_cases = min(max(0, args.llm_cases), len(cases))
    planned_calls = estimate_routing_llm_calls(llm_cases)
    embedding = args.embedding or embedding_provider_from_environment()
    generator = args.generator or primary_llm_from_environment()
    fallback = args.fallback or fallback_llm_from_environment()

    if args.dry_run:
        print_plan(
            processo_id=args.processo_id,
            cases_count=len(cases),
            llm_cases=llm_cases,
            planned_calls=planned_calls,
            embedding=embedding,
            generator=generator,
            fallback=fallback,
            top_k=args.top_k,
        )
        return

    validate_llm_budget(
        planned_calls=planned_calls,
        max_calls=args.max_llm_calls,
        allow_over_limit=args.allow_paid_over_limit,
        parser=parser,
    )
    report = run_routing_benchmark(
        processo_id=args.processo_id,
        cases=cases,
        top_k=args.top_k,
        embedding_model=embedding,
        llm_cases=llm_cases,
        generator_model=generator,
        fallback_model=fallback,
    )
    output_path = Path(args.output)
    write_routing_benchmark_report(report, output_path)
    print(f"Relatorio JSON: {output_path}")
    print(f"Relatorio Markdown: {output_path.with_suffix('.md')}")
    print(
        f"Hit rate bruto/triagem: {report.raw_hit_rate:.4f} / "
        f"{report.routed_hit_rate:.4f}"
    )
    print(f"MRR bruto/triagem: {report.raw_mrr:.4f} / {report.routed_mrr:.4f}")
    print(
        f"Melhorou/piorou/empatou: {report.improved_cases}/"
        f"{report.degraded_cases}/{report.tied_cases}"
    )
    print(f"Fallbacks LLM: {report.llm_fallback_count}")


def estimate_routing_llm_calls(llm_cases: int) -> int:
    return max(0, llm_cases) * 4


def print_plan(
    *,
    processo_id: str,
    cases_count: int,
    llm_cases: int,
    planned_calls: int,
    embedding: str,
    generator: str,
    fallback: str,
    top_k: int,
) -> None:
    print("Plano do benchmark A/B da triagem")
    print(f"Processo: {processo_id}")
    print(f"Casos de recuperacao: {cases_count}")
    print(f"Casos com LLM: {llm_cases}")
    print(f"Top K: {top_k}")
    print(f"Recuperador: {embedding}")
    print(f"Gerador: {generator}")
    print(f"Fallback: {fallback}")
    print(f"Chamadas LLM no pior caso: {planned_calls}")
    print("Nenhuma chamada externa foi feita por causa do --dry-run.")


def _load_or_generate_cases(
    *,
    processo_id: str,
    cases_path: str | None,
    generate_limit: int,
):
    if cases_path:
        return load_evaluation_cases(cases_path)
    connection = connect_database()
    initialize_database(connection)
    try:
        chunks = ChunkRepository(connection).list_for_processo(processo_id)
        return generate_cases_from_chunks(chunks, generate_limit)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
