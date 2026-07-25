from __future__ import annotations

import argparse
import json
from pathlib import Path

from preparador_audiencia.pdf_extraction import extract_pdf_report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extrai texto de um PDF por pagina e gera relatorio de qualidade."
    )
    parser.add_argument("pdf", help="Caminho para o PDF do processo.")
    parser.add_argument(
        "--output",
        "-o",
        help="Arquivo JSON de saida. Se omitido, imprime no terminal.",
    )
    parser.add_argument(
        "--sample-chars",
        type=int,
        default=500,
        help="Quantidade maxima de caracteres da amostra por pagina.",
    )
    parser.add_argument(
        "--no-ocr",
        action="store_true",
        help="Desativa OCR em paginas com imagem e pouco texto.",
    )
    parser.add_argument(
        "--ocr-zoom",
        type=float,
        default=2.0,
        help="Fator de renderizacao da pagina antes do OCR.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Limita a quantidade de paginas processadas, util para smoke tests.",
    )
    args = parser.parse_args()

    report = extract_pdf_report(
        args.pdf,
        sample_chars=args.sample_chars,
        ocr_enabled=not args.no_ocr,
        ocr_zoom=args.ocr_zoom,
        max_pages=args.max_pages,
    )
    content = json.dumps(report.to_dict(), ensure_ascii=False, indent=2)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        print(f"Relatorio salvo em: {output_path}")
        return

    print(content)


if __name__ == "__main__":
    main()
