from __future__ import annotations

import argparse
from pathlib import Path

from preparador_audiencia.question_promotion import promote_review_file, write_review_file
from preparador_audiencia.question_sources import (
    DEFAULT_QUESTION_SOURCE_PATH,
    generate_question_candidates,
    load_question_sources,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cria revisoes e promove perguntas candidatas ao banco oficial."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    review = subparsers.add_parser("criar-revisao")
    review.add_argument("--sources", default=str(DEFAULT_QUESTION_SOURCE_PATH))
    review.add_argument("--area")
    review.add_argument("--audiencia")
    review.add_argument("--source-kind")
    review.add_argument("--official-only", action="store_true")
    review.add_argument("--include-benchmark", action="store_true")
    review.add_argument("--limit", type=int)
    review.add_argument("--output", required=True)

    promote = subparsers.add_parser("promover")
    promote.add_argument("--review", required=True)
    promote.add_argument("--approved-path")

    args = parser.parse_args()
    if args.command == "criar-revisao":
        _create_review(args)
        return
    _promote(args)


def _create_review(args: argparse.Namespace) -> None:
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
    write_review_file(candidates, Path(args.output))
    print(f"Arquivo de revisao criado: {args.output}")
    print(f"Perguntas para revisar: {len(candidates)}")
    print("Altere decision para approved nas perguntas que devem entrar no banco oficial.")


def _promote(args: argparse.Namespace) -> None:
    result = promote_review_file(
        args.review,
        approved_path=args.approved_path,
    )
    print(f"Arquivo de aprovadas: {result.approved_path}")
    print(f"Promovidas: {result.promoted_count}")
    print(f"Ignoradas: {result.skipped_count}")
    print(f"Total aprovado no banco dinamico: {result.total_approved_templates}")


if __name__ == "__main__":
    main()
