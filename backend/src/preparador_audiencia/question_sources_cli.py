from __future__ import annotations

import argparse
from pathlib import Path

from preparador_audiencia.question_sources import (
    DEFAULT_QUESTION_SOURCE_PATH,
    generate_question_candidates,
    load_question_sources,
    render_question_candidates_markdown,
    write_question_candidates,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gera perguntas candidatas a partir de fontes juridicas curadas."
    )
    parser.add_argument("--sources", default=str(DEFAULT_QUESTION_SOURCE_PATH))
    parser.add_argument("--area", help="Filtra por area, como criminal, familia ou geral.")
    parser.add_argument("--audiencia", help="Filtra por tipo de audiencia.")
    parser.add_argument(
        "--source-kind",
        help="Filtra por tipo de fonte, como faq, manual ou dataset.",
    )
    parser.add_argument("--official-only", action="store_true")
    parser.add_argument("--include-benchmark", action="store_true")
    parser.add_argument("--limit", type=int, help="Limita a quantidade de perguntas.")
    parser.add_argument(
        "--format",
        choices=["markdown", "json", "cases-json"],
        default="markdown",
        help="Formato de saida.",
    )
    parser.add_argument("--output", help="Arquivo de destino. Sem isso, imprime Markdown.")
    args = parser.parse_args()

    sources = load_question_sources(args.sources)
    candidates = generate_question_candidates(
        sources,
        area=args.area,
        audiencia=args.audiencia,
        source_kind=args.source_kind,
        official_only=args.official_only,
        include_benchmark=args.include_benchmark,
        limit=args.limit,
    )

    if args.output:
        write_question_candidates(candidates, Path(args.output), output_format=args.format)
        print(f"Perguntas candidatas exportadas: {args.output}")
        print(f"Total: {len(candidates)}")
        return

    if args.format == "markdown":
        print(render_question_candidates_markdown(candidates))
        return

    output = Path("perguntas-candidatas.json")
    if args.format == "cases-json":
        output = Path("perguntas-candidatas.cases.json")
    write_question_candidates(candidates, output, output_format=args.format)
    print(f"Perguntas candidatas exportadas: {output}")
    print(f"Total: {len(candidates)}")


if __name__ == "__main__":
    main()
