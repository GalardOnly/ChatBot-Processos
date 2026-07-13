from __future__ import annotations

import argparse
from pathlib import Path

from preparador_audiencia.evaluation import (
    load_evaluation_cases,
    run_poc_model_evaluation,
    write_report_files,
)


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
            "Exemplos: groq:..., gemini:..., openai:..., deepseek:..."
        ),
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output", default="reports/poc-modelos.json")
    args = parser.parse_args()

    embedding_specs = args.embedding or ["legal-ensemble"]
    cases = load_evaluation_cases(args.cases)
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


if __name__ == "__main__":
    main()
