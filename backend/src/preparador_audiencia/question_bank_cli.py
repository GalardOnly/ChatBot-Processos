from __future__ import annotations

import argparse
from pathlib import Path

from preparador_audiencia.question_bank import (
    list_question_templates,
    render_question_templates_markdown,
    write_question_templates,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lista perguntas sugeridas para preparar audiencia com a PoC."
    )
    parser.add_argument("--area", help="Filtra por area, como criminal, familia ou geral.")
    parser.add_argument("--audiencia", help="Filtra por tipo de audiencia.")
    parser.add_argument("--tag", action="append", default=[], help="Filtra por uma ou mais tags.")
    parser.add_argument("--limit", type=int, help="Limita a quantidade de perguntas.")
    parser.add_argument(
        "--format",
        choices=["markdown", "json", "cases-json"],
        default="markdown",
        help="Formato de saida.",
    )
    parser.add_argument("--output", help="Arquivo de destino. Sem isso, imprime no terminal.")
    args = parser.parse_args()

    templates = list_question_templates(
        area=args.area,
        audiencia=args.audiencia,
        tags=args.tag,
        limit=args.limit,
    )
    if args.output:
        write_question_templates(templates, Path(args.output), output_format=args.format)
        print(f"Perguntas exportadas: {args.output}")
        return

    if args.format == "markdown":
        print(render_question_templates_markdown(templates))
        return

    suffix = ".json" if args.format == "json" else ".cases.json"
    output = Path(f"perguntas-audiencia{suffix}")
    write_question_templates(templates, output, output_format=args.format)
    print(f"Perguntas exportadas: {output}")


if __name__ == "__main__":
    main()
