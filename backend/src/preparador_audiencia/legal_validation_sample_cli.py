from __future__ import annotations

import argparse
from pathlib import Path

from preparador_audiencia.legal_validation_sample import (
    approve_anonymized_candidate,
    create_legal_review_worksheet,
    finalize_legal_review_worksheet,
    prepare_anonymized_candidate,
    verify_anonymized_candidate,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepara uma amostra real anonimizada para revisao juridica."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser(
        "preparar",
        help="Cria um PDF candidato e um manifesto sem dados originais.",
    )
    prepare_parser.add_argument("--pdf", required=True)
    prepare_parser.add_argument("--config", required=True)
    prepare_parser.add_argument(
        "--output-root",
        default="../samples/anonimizados",
    )
    prepare_parser.add_argument("--overwrite", action="store_true")

    verify_parser = subparsers.add_parser(
        "verificar",
        help="Repete a busca de residuos depois de uma revisao manual.",
    )
    verify_parser.add_argument("--manifest", required=True)
    verify_parser.add_argument("--config", required=True)

    approve_parser = subparsers.add_parser(
        "aprovar-anonimizacao",
        help="Registra a revisao humana integral do PDF candidato.",
    )
    approve_parser.add_argument("--manifest", required=True)
    approve_parser.add_argument("--reviewer", required=True)
    approve_parser.add_argument("--confirm-authorization", action="store_true")
    approve_parser.add_argument("--confirm-all-pages", action="store_true")
    approve_parser.add_argument("--confirm-images", action="store_true")

    worksheet_parser = subparsers.add_parser(
        "criar-ficha",
        help="Cria a ficha de perguntas para dois revisores juridicos.",
    )
    worksheet_parser.add_argument("--manifest", required=True)
    worksheet_parser.add_argument("--output")

    finalize_parser = subparsers.add_parser(
        "finalizar-ficha",
        help="Valida duas revisoes e cria a suite de referencia local.",
    )
    finalize_parser.add_argument("--worksheet", required=True)
    finalize_parser.add_argument("--config", required=True)
    finalize_parser.add_argument("--output")

    args = parser.parse_args()
    if args.command == "preparar":
        manifest = prepare_anonymized_candidate(
            source_pdf=args.pdf,
            config_path=args.config,
            output_root=args.output_root,
            overwrite=args.overwrite,
        )
        print(f"Manifesto: {manifest}")
        _print_manifest_summary(manifest)
        return

    if args.command == "verificar":
        manifest = verify_anonymized_candidate(args.manifest, args.config)
        print(f"Status: {manifest['status']}")
        print(f"Residuos: {len(manifest['residual_identifiers'])}")
        print(f"Paginas para revisao visual: {len(manifest['visual_review_pages'])}")
        return

    if args.command == "aprovar-anonimizacao":
        manifest = approve_anonymized_candidate(
            args.manifest,
            reviewer=args.reviewer,
            authorization_confirmed=args.confirm_authorization,
            all_pages_reviewed=args.confirm_all_pages,
            images_reviewed=args.confirm_images,
        )
        print(f"Status: {manifest['status']}")
        print("A anonimizacao foi liberada apenas para o benchmark local.")
        return

    if args.command == "criar-ficha":
        output = create_legal_review_worksheet(args.manifest, args.output)
        print(f"Ficha: {output}")
        print(
            "Inclua paginas e termos ou justifique a exclusao; "
            "sempre registre duas revisoes."
        )
        return

    if args.command == "finalizar-ficha":
        output = finalize_legal_review_worksheet(
            args.worksheet,
            args.config,
            args.output,
        )
        print(f"Suite de referencia: {output}")


def _print_manifest_summary(path: Path) -> None:
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    print(f"Status: {payload['status']}")
    print(f"Paginas: {payload['page_count']}")
    print(f"Identificadores detectados: {len(payload['detected_identifiers'])}")
    print(f"Residuos: {len(payload['residual_identifiers'])}")
    print(f"Paginas para revisao visual: {len(payload['visual_review_pages'])}")


if __name__ == "__main__":
    main()
