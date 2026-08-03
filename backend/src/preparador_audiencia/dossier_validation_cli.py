from __future__ import annotations

import argparse
from pathlib import Path

from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.dossier_validation import (
    validate_hearing_dossier,
    write_dossier_validation_report,
)
from preparador_audiencia.environment import load_environment
from preparador_audiencia.eval_cli import validate_llm_budget
from preparador_audiencia.hearing_dossier import generate_hearing_dossier
from preparador_audiencia.hearing_dossier_repository import HearingDossierRepository
from preparador_audiencia.repositories import ProcessoRepository
from preparador_audiencia.settings import (
    dossier_fallback_llm_from_environment,
    embedding_provider_from_environment,
    primary_llm_from_environment,
)

DEFAULT_MAX_LLM_CALLS = 6


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gera e valida o dossie de audiencia contra os chunks persistidos."
    )
    parser.add_argument("--processo-id", required=True)
    parser.add_argument("--top-k", type=int, default=18)
    parser.add_argument("--regenerar", action="store_true")
    parser.add_argument("--somente-validar", action="store_true")
    parser.add_argument("--lexical-only", action="store_true")
    parser.add_argument("--delay-seconds", type=float, default=0.0)
    parser.add_argument("--output", default="reports/validacao-dossie.json")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--max-llm-calls", type=int, default=DEFAULT_MAX_LLM_CALLS)
    parser.add_argument("--allow-paid-over-limit", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_environment(args.env_file)
    planned_calls = 0 if args.somente_validar else 6
    if args.dry_run:
        _print_plan(args, planned_calls)
        return
    validate_llm_budget(
        planned_calls=planned_calls,
        max_calls=args.max_llm_calls,
        allow_over_limit=args.allow_paid_over_limit,
        parser=parser,
    )

    connection = connect_database()
    initialize_database(connection)
    try:
        processo = ProcessoRepository(connection).get(args.processo_id)
        if processo is None:
            parser.error("Processo nao encontrado.")
        if processo.status != "concluido":
            parser.error("O processo precisa estar concluido para validar o dossie.")

        repository = HearingDossierRepository(connection)
        if args.somente_validar:
            dossier = repository.get(args.processo_id)
            if dossier is None:
                parser.error("O dossie ainda nao foi gerado.")
        else:
            dossier = generate_hearing_dossier(
                args.processo_id,
                repository,
                top_k=args.top_k,
                lexical_only=args.lexical_only,
                regenerate=args.regenerar,
                section_delay_seconds=max(0.0, args.delay_seconds),
            )
        report = validate_hearing_dossier(dossier, connection)
        json_path, markdown_path = write_dossier_validation_report(
            report,
            Path(args.output),
        )
    finally:
        connection.close()

    print(f"Relatorio JSON: {json_path}")
    print(f"Relatorio Markdown: {markdown_path}")
    print(f"Status do dossie: {report.dossier_status}")
    print(f"Veredito tecnico: {report.verdict}")
    print(
        f"Referencias validas: {report.valid_references}/{report.reference_checks} "
        f"({report.reference_accuracy:.1%})"
    )
    print(
        f"Trechos literais validos: {report.valid_literals}/{report.literal_checks} "
        f"({report.literal_accuracy:.1%})"
    )
    print(f"Achados para revisao: {len(report.findings)}")


def _print_plan(args: argparse.Namespace, planned_calls: int) -> None:
    print("Plano de validacao do dossie")
    print(f"Processo: {args.processo_id}")
    print(f"Top K por secao: {args.top_k}")
    print(f"Modelo principal: {primary_llm_from_environment()}")
    print(f"Fallback: {dossier_fallback_llm_from_environment()}")
    print(f"Recuperador: {embedding_provider_from_environment()}")
    print(f"Somente busca lexical: {args.lexical_only}")
    print(f"Espera entre secoes pendentes: {max(0.0, args.delay_seconds):.1f}s")
    print(f"Chamadas LLM planejadas no pior caso: {planned_calls}")
    print(f"Limite atual: {args.max_llm_calls}")
    print("Nenhuma chamada externa foi feita por causa do --dry-run.")


if __name__ == "__main__":
    main()
