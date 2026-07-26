from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

from preparador_audiencia.benchmark import (
    download_pdf_sources,
    load_benchmark_sources,
    render_sources_table,
    run_juristcu_benchmark,
    run_pdf_benchmark,
    sources_by_kind,
    write_juristcu_report,
    write_pdf_benchmark_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gerencia fontes publicas para benchmark da PoC."
    )
    parser.add_argument(
        "--manifest",
        default="benchmark_sources.example.json",
        help="Arquivo JSON com fontes candidatas para benchmark.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("listar", help="Lista fontes cadastradas.")
    list_parser.add_argument("--kind", choices=["dataset", "pdf", "html"], default=None)

    download_parser = subparsers.add_parser(
        "baixar-pdfs",
        help="Baixa fontes do tipo PDF com URL direta.",
    )
    download_parser.add_argument("--output", default="../samples/benchmark")
    download_parser.add_argument("--report", default="reports/benchmark-downloads.json")

    juristcu_parser = subparsers.add_parser(
        "juristcu",
        help="Roda benchmark de recuperacao no dataset JurisTCU.",
    )
    juristcu_parser.add_argument("--cache", default="../samples/benchmark/juristcu")
    juristcu_parser.add_argument("--queries", type=int, default=5)
    juristcu_parser.add_argument("--distractors", type=int, default=250)
    juristcu_parser.add_argument("--embedding", default="hash")
    juristcu_parser.add_argument("--top-k", type=int, default=10)
    juristcu_parser.add_argument("--output", default="reports/juristcu-benchmark.json")
    juristcu_parser.add_argument(
        "--reindex",
        action="store_true",
        help="Forca recriacao dos indices mesmo quando ja existe cache compativel.",
    )

    pdf_parser = subparsers.add_parser(
        "pdfs",
        help="Roda benchmark de extracao/OCR em PDFs locais.",
    )
    pdf_parser.add_argument("paths", nargs="+", help="Arquivos ou globs de PDFs.")
    pdf_parser.add_argument("--family", default="pdfs-publicos")
    pdf_parser.add_argument("--no-ocr", action="store_true")
    pdf_parser.add_argument("--max-pages", type=int, default=None)
    pdf_parser.add_argument("--output", default="reports/pdf-benchmark.json")

    args = parser.parse_args()
    sources = load_benchmark_sources(args.manifest) if args.command != "juristcu" else []

    if args.command == "listar":
        selected = sources_by_kind(sources, args.kind)
        print(render_sources_table(selected))
        return

    if args.command == "baixar-pdfs":
        selected = sources_by_kind(sources, "pdf")
        results = download_pdf_sources(selected, args.output)
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps([result.to_dict() for result in results], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        for result in results:
            status = "ignorado" if result.skipped else "baixado"
            print(f"{status}: {result.source_id} - {result.message}")
        print(f"Relatorio: {report_path}")
        return

    if args.command == "juristcu":
        report = run_juristcu_benchmark(
            cache_dir=args.cache,
            query_limit=args.queries,
            distractor_limit=args.distractors,
            embedding_model=args.embedding,
            top_k=args.top_k,
            reindex=args.reindex,
        )
        write_juristcu_report(report, args.output)
        print(f"Dataset: {report.dataset}")
        print(f"Embedding: {report.embedding_model}")
        print(f"Documentos indexados: {report.indexed_documents}")
        print(
            "Indices reaproveitados: "
            f"{', '.join(report.reused_indexes) if report.reused_indexes else 'nenhum'}"
        )
        print(
            "Indices recriados: "
            f"{', '.join(report.rebuilt_indexes) if report.rebuilt_indexes else 'nenhum'}"
        )
        print(f"Consultas avaliadas: {report.query_count}")
        print(f"Hit rate: {report.hit_rate:.4f}")
        print(f"MRR: {report.mean_reciprocal_rank:.4f}")
        print(f"Precisao media no Top K: {report.mean_precision_at_k:.4f}")
        print(f"Relatorio JSON: {args.output}")
        print(f"Relatorio Markdown: {Path(args.output).with_suffix('.md')}")
        return

    if args.command == "pdfs":
        paths = _expand_paths(args.paths)
        report = run_pdf_benchmark(
            paths,
            family=args.family,
            ocr_enabled=not args.no_ocr,
            max_pages=args.max_pages,
        )
        write_pdf_benchmark_report(report, args.output)
        print(f"Familia: {report.family}")
        print(f"Arquivos avaliados: {len(report.files)}")
        for file_result in report.files:
            print(
                f"{file_result.file_name}: {file_result.processed_pages} paginas, "
                f"{file_result.total_char_count} caracteres, "
                f"{file_result.ocr_page_count} paginas com OCR"
            )
        print(f"Relatorio JSON: {args.output}")
        print(f"Relatorio Markdown: {Path(args.output).with_suffix('.md')}")


def _expand_paths(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        matches = [Path(match) for match in glob.glob(pattern)]
        paths.extend(matches or [Path(pattern)])
    return paths


if __name__ == "__main__":
    main()
