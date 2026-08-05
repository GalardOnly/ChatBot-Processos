from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import fitz

from preparador_audiencia.reference_benchmark import pdf_text_sha256
from preparador_audiencia.reference_suite import (
    ReferenceCase,
    ReferenceProcess,
    ReferenceSuite,
    write_reference_suite,
)

CONFIG_SCHEMA_VERSION = "1.0"
MANIFEST_SCHEMA_VERSION = "1.0"
WORKSHEET_SCHEMA_VERSION = "1.0"
MINIMUM_LEGAL_REVIEWERS = 2
MIN_ALIAS_VALUE_LENGTH = 4

STATUS_BLOCKED = "bloqueado_residuo"
STATUS_VISUAL_REVIEW = "revisao_visual_obrigatoria"
STATUS_HUMAN_REVIEW = "revisao_humana_pendente"
STATUS_APPROVED = "aprovado_para_benchmark"

_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_DOMAIN_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


@dataclass(frozen=True)
class AliasRule:
    id: str
    replacement: str
    values: tuple[str, ...]


@dataclass(frozen=True)
class ValidationSampleConfig:
    case_id: str
    domain: str
    authorization_reference: str
    aliases: tuple[AliasRule, ...]


@dataclass(frozen=True)
class IdentifierPattern:
    category: str
    replacement: str
    regex: re.Pattern[str]


IDENTIFIER_PATTERNS = (
    IdentifierPattern(
        "numero_processo",
        "[PROCESSO REMOVIDO]",
        re.compile(r"(?<!\d)\d{7}-?\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}(?!\d)"),
    ),
    IdentifierPattern(
        "cpf",
        "[CPF REMOVIDO]",
        re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)"),
    ),
    IdentifierPattern(
        "cnpj",
        "[CNPJ REMOVIDO]",
        re.compile(r"(?<!\d)\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?!\d)"),
    ),
    IdentifierPattern(
        "email",
        "[EMAIL REMOVIDO]",
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    ),
    IdentifierPattern(
        "telefone",
        "[TELEFONE REMOVIDO]",
        re.compile(r"(?<!\d)(?:\+?55\s*)?\(?\d{2}\)?\s*9?\d{4}[-\s]?\d{4}(?!\d)"),
    ),
    IdentifierPattern(
        "cep",
        "[CEP REMOVIDO]",
        re.compile(r"(?<!\d)\d{5}-?\d{3}(?!\d)"),
    ),
)

DEFAULT_REVIEW_QUESTIONS = (
    (
        "resumo_fatos",
        "Qual e o resumo dos fatos relevantes para a audiencia?",
    ),
    (
        "data_local_fato",
        "Qual foi a data, o horario e o local do fato, quando localizados?",
    ),
    (
        "acusacao_artigos",
        "Quais imputacoes, artigos e penas maximas aparecem no processo?",
    ),
    (
        "recebimento_denuncia",
        "Quando a denuncia foi recebida e em qual pagina isso consta?",
    ),
    (
        "suspensao_processo",
        "Houve suspensao do processo e quais foram o inicio, o fim e o fundamento?",
    ),
    (
        "prisao_cautelares",
        "Houve flagrante, prisao ou medida cautelar e qual e a situacao atual?",
    ),
    (
        "depoimentos",
        "Quais depoimentos existem e quais trechos literais sao relevantes?",
    ),
    (
        "contradicoes",
        "Quais contradicoes ou divergencias aparecem entre os depoimentos?",
    ),
    (
        "provas",
        "Quais provas e documentos sustentam ou enfraquecem a acusacao?",
    ),
    (
        "prescricao",
        "Quais dados do processo sao necessarios para conferir a prescricao?",
    ),
    (
        "teses_defensivas",
        "Quais teses defensivas possuem apoio em fatos e paginas do processo?",
    ),
    (
        "nulidades",
        "Ha indicios de nulidade e quais requisitos ainda precisam ser confirmados?",
    ),
)


def load_validation_sample_config(path: str | Path) -> ValidationSampleConfig:
    config_path = Path(path)
    payload = _load_mapping(config_path)
    _require_exact_fields(
        payload,
        required={"schema_version", "case_id", "domain", "authorization", "aliases"},
        context="configuracao",
    )
    if payload["schema_version"] != CONFIG_SCHEMA_VERSION:
        raise ValueError(f"schema_version deve ser {CONFIG_SCHEMA_VERSION}")

    case_id = _require_identifier(payload.get("case_id"), "case_id", _ID_PATTERN)
    domain = _require_identifier(payload.get("domain"), "domain", _DOMAIN_PATTERN)
    authorization = _require_mapping(payload.get("authorization"), "authorization")
    _require_exact_fields(
        authorization,
        required={"confirmed", "reference"},
        context="authorization",
    )
    if authorization.get("confirmed") is not True:
        raise ValueError("A autorizacao precisa estar confirmada antes da preparacao.")
    authorization_reference = _require_identifier(
        authorization.get("reference"),
        "authorization.reference",
        _ID_PATTERN,
    )

    raw_aliases = payload.get("aliases")
    if not isinstance(raw_aliases, list) or not raw_aliases:
        raise ValueError("aliases deve ser uma lista nao vazia")
    aliases = tuple(
        _alias_from_mapping(item, index) for index, item in enumerate(raw_aliases)
    )
    _ensure_unique((alias.id for alias in aliases), "alias.id")
    normalized_values = [
        _normalized_identifier(value) for alias in aliases for value in alias.values
    ]
    _ensure_unique(normalized_values, "alias.values")
    return ValidationSampleConfig(
        case_id=case_id,
        domain=domain,
        authorization_reference=authorization_reference,
        aliases=aliases,
    )


def prepare_anonymized_candidate(
    source_pdf: str | Path,
    config_path: str | Path,
    output_root: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    config_file = Path(config_path)
    config = load_validation_sample_config(config_file)
    source = Path(source_pdf)
    if not source.is_file():
        raise FileNotFoundError(f"PDF de origem nao encontrado: {source}")

    case_dir = Path(output_root) / config.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = case_dir / f"{config.case_id}-anonimizado-candidato.pdf"
    manifest_path = case_dir / "manifesto-anonimizacao.json"
    if not overwrite and (candidate_path.exists() or manifest_path.exists()):
        raise FileExistsError(
            "A amostra ja existe. Use overwrite somente depois de conferir o destino."
        )

    source_bytes = source.read_bytes()
    detected: dict[tuple[str, int], int] = {}
    alias_hits: dict[tuple[str, int], int] = {}
    visual_review_pages: set[int] = set()
    unlocated_matches: dict[tuple[str, int], int] = {}
    removed_annotations = 0
    removed_form_fields = 0

    with fitz.open(stream=source_bytes, filetype="pdf") as document:
        if document.needs_pass:
            raise ValueError("PDF protegido por senha nao pode entrar na amostra.")
        removed_attachments = _remove_embedded_files(document)
        _clear_pdf_metadata(document)
        for page_index, page in enumerate(document, start=1):
            native_text = page.get_text("text")
            if page.get_images(full=True):
                visual_review_pages.add(page_index)
            removed_annotations += _remove_annotations(page)
            removed_form_fields += _remove_widgets(page)
            _redact_page(
                page,
                native_text=native_text,
                page_number=page_index,
                config=config,
                detected=detected,
                alias_hits=alias_hits,
                unlocated_matches=unlocated_matches,
            )
        document.save(
            candidate_path,
            garbage=4,
            clean=True,
            deflate=True,
        )

    verification = _verify_candidate(candidate_path, config)
    status = _candidate_status(
        verification["residual_identifiers"],
        verification["structural_residuals"],
        visual_review_pages,
    )
    warnings = [
        "O candidato nunca e considerado anonimo sem revisao humana integral.",
        "Valores originais e o PDF de origem permanecem fora do manifesto.",
    ]
    if visual_review_pages:
        warnings.append(
            "Paginas com imagens exigem conferencia visual; texto dentro da imagem "
            "nao e aprovado automaticamente."
        )
    if unlocated_matches:
        warnings.append(
            "Houve texto detectado sem retangulo localizavel; a verificacao residual "
            "decide se o candidato permanece bloqueado."
        )

    now = _now()
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "case_id": config.case_id,
        "domain": config.domain,
        "authorization": {
            "confirmed": True,
            "reference": config.authorization_reference,
        },
        "source_sha256": _bytes_sha256(source_bytes),
        "config_sha256": _file_sha256(config_file),
        "candidate_document": candidate_path.name,
        "candidate_sha256": _file_sha256(candidate_path),
        "page_count": verification["page_count"],
        "status": status,
        "detected_identifiers": _counts_to_list(detected),
        "alias_hits": _alias_counts_to_list(alias_hits),
        "unlocated_matches": _counts_to_list(unlocated_matches),
        "residual_identifiers": verification["residual_identifiers"],
        "structural_residuals": verification["structural_residuals"],
        "visual_review_pages": sorted(visual_review_pages),
        "removed_annotations": removed_annotations,
        "removed_form_fields": removed_form_fields,
        "removed_attachments": removed_attachments,
        "human_review": {
            "status": "pending",
            "reviewer": None,
            "reviewed_at": None,
        },
        "created_at": now,
        "verified_at": now,
        "warnings": warnings,
    }
    _write_json(manifest, manifest_path)
    return manifest_path


def verify_anonymized_candidate(
    manifest_path: str | Path,
    config_path: str | Path,
) -> dict[str, Any]:
    path = Path(manifest_path)
    manifest = _load_manifest(path)
    config_file = Path(config_path)
    config = load_validation_sample_config(config_file)
    if config.case_id != manifest["case_id"]:
        raise ValueError("A configuracao pertence a outro caso.")
    if _file_sha256(config_file) != manifest["config_sha256"]:
        raise ValueError("A configuracao foi alterada desde a preparacao.")

    candidate = _candidate_path(path, manifest)
    verification = _verify_candidate(candidate, config)
    manifest["candidate_sha256"] = _file_sha256(candidate)
    manifest["page_count"] = verification["page_count"]
    manifest["residual_identifiers"] = verification["residual_identifiers"]
    manifest["structural_residuals"] = verification["structural_residuals"]
    manifest["status"] = _candidate_status(
        verification["residual_identifiers"],
        verification["structural_residuals"],
        set(manifest["visual_review_pages"]),
    )
    manifest["human_review"] = {
        "status": "pending",
        "reviewer": None,
        "reviewed_at": None,
    }
    manifest["verified_at"] = _now()
    _write_json(manifest, path)
    return manifest


def approve_anonymized_candidate(
    manifest_path: str | Path,
    *,
    reviewer: str,
    authorization_confirmed: bool,
    all_pages_reviewed: bool,
    images_reviewed: bool,
) -> dict[str, Any]:
    path = Path(manifest_path)
    manifest = _load_manifest(path)
    reviewer_id = _require_identifier(reviewer, "reviewer", _ID_PATTERN)
    if manifest["status"] == STATUS_BLOCKED:
        raise ValueError("O candidato ainda possui residuos e nao pode ser aprovado.")
    if not authorization_confirmed:
        raise ValueError("Confirme a autorizacao para uso no benchmark.")
    if not all_pages_reviewed:
        raise ValueError("A revisao humana precisa cobrir todas as paginas.")
    if manifest["visual_review_pages"] and not images_reviewed:
        raise ValueError("As paginas com imagens precisam de revisao visual explicita.")
    candidate = _candidate_path(path, manifest)
    if _file_sha256(candidate) != manifest["candidate_sha256"]:
        raise ValueError("O PDF candidato mudou; execute verificar novamente.")

    reviewed_at = _now()
    manifest["status"] = STATUS_APPROVED
    manifest["human_review"] = {
        "status": "approved",
        "reviewer": reviewer_id,
        "reviewed_at": reviewed_at,
        "authorization_confirmed": True,
        "all_pages_reviewed": True,
        "images_reviewed": bool(images_reviewed),
    }
    _write_json(manifest, path)
    return manifest


def create_legal_review_worksheet(
    manifest_path: str | Path,
    output_path: str | Path | None = None,
) -> Path:
    path = Path(manifest_path)
    manifest = _load_manifest(path)
    if manifest["status"] != STATUS_APPROVED:
        raise ValueError("A anonimizacao precisa estar aprovada antes da ficha juridica.")
    candidate = _candidate_path(path, manifest)
    if _file_sha256(candidate) != manifest["candidate_sha256"]:
        raise ValueError("O PDF candidato mudou depois da aprovacao.")

    target = Path(output_path) if output_path else path.parent / "ficha-revisao-juridica.json"
    worksheet = {
        "schema_version": WORKSHEET_SCHEMA_VERSION,
        "case_id": manifest["case_id"],
        "domain": manifest["domain"],
        "document": manifest["candidate_document"],
        "sha256": manifest["candidate_sha256"],
        "config_sha256": manifest["config_sha256"],
        "status": "pending",
        "minimum_reviewers": MINIMUM_LEGAL_REVIEWERS,
        "questions": [
            {
                "id": question_id,
                "pergunta": question,
                "include_in_benchmark": True,
                "exclusion_reason": "",
                "expected_pages": [],
                "expected_terms": [],
                "response_relevant_pages": [],
                "response_expected_terms": [],
                "review_notes": "",
                "reviews": [],
            }
            for question_id, question in DEFAULT_REVIEW_QUESTIONS
        ],
        "created_at": _now(),
        "finalized_at": None,
    }
    _write_json(worksheet, target)
    return target


def finalize_legal_review_worksheet(
    worksheet_path: str | Path,
    config_path: str | Path,
    output_path: str | Path | None = None,
) -> Path:
    path = Path(worksheet_path)
    worksheet = _load_mapping(path)
    _validate_worksheet_header(worksheet)
    config_file = Path(config_path)
    config = load_validation_sample_config(config_file)
    if config.case_id != worksheet["case_id"]:
        raise ValueError("A configuracao pertence a outro caso.")
    if _file_sha256(config_file) != worksheet["config_sha256"]:
        raise ValueError("A configuracao foi alterada desde a criacao da ficha.")
    candidate = path.parent / str(worksheet["document"])
    if not candidate.is_file():
        raise FileNotFoundError(f"PDF candidato nao encontrado: {candidate}")
    if _file_sha256(candidate) != worksheet["sha256"]:
        raise ValueError("O PDF candidato mudou desde a criacao da ficha.")
    with fitz.open(candidate) as document:
        page_count = document.page_count

    cases = []
    for item in _require_list(worksheet.get("questions"), "questions"):
        reference_case = _reference_case_from_review(
            item,
            MINIMUM_LEGAL_REVIEWERS,
            config.aliases,
            page_count,
        )
        if reference_case is not None:
            cases.append(reference_case)
    if not cases:
        raise ValueError("A ficha precisa incluir ao menos uma pergunta no benchmark.")
    process = ReferenceProcess(
        id=str(worksheet["case_id"]),
        domain=str(worksheet["domain"]),
        document=str(worksheet["document"]),
        source="Amostra real anonimizada com revisao humana independente",
        source_url=None,
        sha256=str(worksheet["sha256"]),
        text_sha256=pdf_text_sha256(candidate.read_bytes()),
        cases=cases,
    )
    suite = ReferenceSuite(
        id=f"validacao-{worksheet['case_id']}-v1",
        description="Amostra real anonimizada e revisada para validacao juridica.",
        processes=[process],
    )
    target = Path(output_path) if output_path else path.parent / "suite-referencia.json"
    write_reference_suite(suite, target)
    worksheet["status"] = "approved"
    worksheet["finalized_at"] = _now()
    worksheet["reference_suite"] = target.name
    _write_json(worksheet, path)
    return target


def _redact_page(
    page: fitz.Page,
    *,
    native_text: str,
    page_number: int,
    config: ValidationSampleConfig,
    detected: dict[tuple[str, int], int],
    alias_hits: dict[tuple[str, int], int],
    unlocated_matches: dict[tuple[str, int], int],
) -> None:
    rectangles: set[tuple[float, float, float, float]] = set()
    has_redactions = False
    for alias in config.aliases:
        for value in alias.values:
            occurrences = _casefold_count(native_text, value)
            if not occurrences:
                continue
            alias_hits[(alias.id, page_number)] = (
                alias_hits.get((alias.id, page_number), 0) + occurrences
            )
            rects = page.search_for(value)
            if not rects:
                unlocated_matches[(f"alias:{alias.id}", page_number)] = occurrences
            has_redactions = _add_redaction_rectangles(
                page,
                rects,
                replacement=alias.replacement,
                rectangles=rectangles,
            ) or has_redactions

    for identifier in IDENTIFIER_PATTERNS:
        matches = [match.group(0) for match in identifier.regex.finditer(native_text)]
        if not matches:
            continue
        detected[(identifier.category, page_number)] = len(matches)
        for value in matches:
            rects = page.search_for(value)
            if not rects:
                key = (identifier.category, page_number)
                unlocated_matches[key] = unlocated_matches.get(key, 0) + 1
            has_redactions = _add_redaction_rectangles(
                page,
                rects,
                replacement=identifier.replacement,
                rectangles=rectangles,
            ) or has_redactions
    if has_redactions:
        page.apply_redactions()


def _add_redaction_rectangles(
    page: fitz.Page,
    rects: list[fitz.Rect],
    *,
    replacement: str,
    rectangles: set[tuple[float, float, float, float]],
) -> bool:
    added = False
    for rect in rects:
        key = tuple(round(value, 2) for value in (rect.x0, rect.y0, rect.x1, rect.y1))
        if key in rectangles:
            continue
        rectangles.add(key)
        page.add_redact_annot(
            rect,
            text=replacement,
            fontname="helv",
            fontsize=6,
            fill=(1, 1, 1),
            text_color=(0, 0, 0),
            cross_out=False,
        )
        added = True
    return added


def _verify_candidate(
    candidate: Path,
    config: ValidationSampleConfig,
) -> dict[str, object]:
    residuals: dict[tuple[str, int], int] = {}
    structural: dict[tuple[str, int], int] = {}
    with fitz.open(candidate) as document:
        privacy_metadata_fields = (
            "title",
            "author",
            "subject",
            "keywords",
            "creator",
            "producer",
            "creationDate",
            "modDate",
            "trapped",
        )
        metadata_values = [
            document.metadata.get(field)
            for field in privacy_metadata_fields
            if document.metadata.get(field)
        ]
        if metadata_values:
            structural[("metadados_pdf", 0)] = len(metadata_values)
        attachments = list(document.embfile_names())
        if attachments:
            structural[("arquivos_anexados", 0)] = len(attachments)
        for page_number, page in enumerate(document, start=1):
            text = page.get_text("text")
            for alias in config.aliases:
                for value in alias.values:
                    if _normalized_identifier(value) in _normalized_identifier(text):
                        key = (f"alias:{alias.id}", page_number)
                        residuals[key] = residuals.get(key, 0) + 1
            for identifier in IDENTIFIER_PATTERNS:
                count = len(identifier.regex.findall(text))
                if count:
                    residuals[(identifier.category, page_number)] = count
            annotations = list(page.annots() or [])
            widgets = list(page.widgets() or [])
            if annotations:
                structural[("anotacoes_pdf", page_number)] = len(annotations)
            if widgets:
                structural[("campos_formulario", page_number)] = len(widgets)
        return {
            "page_count": document.page_count,
            "residual_identifiers": _counts_to_list(residuals),
            "structural_residuals": _counts_to_list(structural),
        }


def _candidate_status(
    residuals: list[dict[str, object]],
    structural_residuals: list[dict[str, object]],
    visual_review_pages: set[int],
) -> str:
    if residuals or structural_residuals:
        return STATUS_BLOCKED
    if visual_review_pages:
        return STATUS_VISUAL_REVIEW
    return STATUS_HUMAN_REVIEW


def _reference_case_from_review(
    value: object,
    minimum_reviewers: int,
    aliases: tuple[AliasRule, ...],
    page_count: int,
) -> ReferenceCase | None:
    item = _require_mapping(value, "question")
    question_id = _require_identifier(item.get("id"), "question.id", _ID_PATTERN)
    question = _require_text(item.get("pergunta"), "question.pergunta")
    include_in_benchmark = item.get("include_in_benchmark")
    if not isinstance(include_in_benchmark, bool):
        raise ValueError("include_in_benchmark deve ser verdadeiro ou falso")
    unique_reviewers, review_notes = _approved_reviews(
        item.get("reviews"),
        question_id,
        minimum_reviewers,
    )
    if not include_in_benchmark:
        exclusion_reason = _require_text(
            item.get("exclusion_reason"),
            "exclusion_reason",
        )
        _ensure_no_direct_identifiers(
            [question, exclusion_reason, *review_notes],
            aliases,
        )
        return None

    pages = _positive_sorted_ints(item.get("expected_pages"), "expected_pages")
    terms = _non_empty_texts(item.get("expected_terms"), "expected_terms")
    response_pages = _positive_sorted_ints(
        item.get("response_relevant_pages"),
        "response_relevant_pages",
    )
    _ensure_pages_exist(pages, page_count, question_id, "expected_pages")
    _ensure_pages_exist(
        response_pages,
        page_count,
        question_id,
        "response_relevant_pages",
    )
    response_terms = _non_empty_texts(
        item.get("response_expected_terms"),
        "response_expected_terms",
    )
    exclusion_reason = str(item.get("exclusion_reason") or "").strip()
    if exclusion_reason:
        raise ValueError(
            f"A pergunta {question_id} esta incluida e nao deve ter exclusion_reason."
        )
    _ensure_no_direct_identifiers(
        [question, *terms, *response_terms, *review_notes],
        aliases,
    )
    return ReferenceCase(
        id=question_id,
        pergunta=question,
        expected_pages=pages,
        expected_terms=terms,
        response_relevant_pages=response_pages,
        response_expected_terms=response_terms,
        review_status="approved",
        reviewer=", ".join(unique_reviewers),
        review_notes=" | ".join(review_notes) or "Revisao independente concluida.",
    )


def _approved_reviews(
    value: object,
    question_id: str,
    minimum_reviewers: int,
) -> tuple[list[str], list[str]]:
    reviews = _require_list(value, "reviews")
    approved_reviewers = []
    review_notes = []
    for raw_review in reviews:
        review = _require_mapping(raw_review, "review")
        reviewer = _require_identifier(review.get("reviewer"), "reviewer", _ID_PATTERN)
        decision = _require_text(review.get("decision"), "decision")
        if decision == "rejected":
            raise ValueError(f"A pergunta {question_id} possui revisao rejeitada.")
        if decision != "approved":
            raise ValueError("decision deve ser approved ou rejected")
        approved_reviewers.append(reviewer)
        note = str(review.get("notes") or "").strip()
        if note:
            review_notes.append(f"{reviewer}: {note}")
    unique_reviewers = sorted(set(approved_reviewers))
    if len(unique_reviewers) < minimum_reviewers:
        raise ValueError(
            f"A pergunta {question_id} precisa de {minimum_reviewers} revisores "
            "independentes."
        )
    return unique_reviewers, review_notes


def _validate_worksheet_header(worksheet: dict[str, Any]) -> None:
    if worksheet.get("schema_version") != WORKSHEET_SCHEMA_VERSION:
        raise ValueError(f"schema_version deve ser {WORKSHEET_SCHEMA_VERSION}")
    _require_identifier(worksheet.get("case_id"), "case_id", _ID_PATTERN)
    _require_identifier(worksheet.get("domain"), "domain", _DOMAIN_PATTERN)
    document = _require_text(worksheet.get("document"), "document")
    if Path(document).name != document or not document.lower().endswith(".pdf"):
        raise ValueError("document deve ser apenas o nome de um PDF")
    digest = _require_text(worksheet.get("sha256"), "sha256")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("sha256 deve ser hexadecimal com 64 caracteres")
    config_digest = _require_text(worksheet.get("config_sha256"), "config_sha256")
    if not re.fullmatch(r"[0-9a-f]{64}", config_digest):
        raise ValueError("config_sha256 deve ser hexadecimal com 64 caracteres")
    minimum = worksheet.get("minimum_reviewers")
    if minimum != MINIMUM_LEGAL_REVIEWERS:
        raise ValueError(
            f"minimum_reviewers deve permanecer em {MINIMUM_LEGAL_REVIEWERS}"
        )


def _load_manifest(path: Path) -> dict[str, Any]:
    manifest = _load_mapping(path)
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"schema_version deve ser {MANIFEST_SCHEMA_VERSION}")
    _require_identifier(manifest.get("case_id"), "case_id", _ID_PATTERN)
    document = _require_text(manifest.get("candidate_document"), "candidate_document")
    if Path(document).name != document or not document.lower().endswith(".pdf"):
        raise ValueError("candidate_document deve ser apenas o nome de um PDF")
    return manifest


def _candidate_path(manifest_path: Path, manifest: dict[str, Any]) -> Path:
    candidate = manifest_path.parent / str(manifest["candidate_document"])
    if not candidate.is_file():
        raise FileNotFoundError(f"PDF candidato nao encontrado: {candidate}")
    return candidate


def _alias_from_mapping(value: object, index: int) -> AliasRule:
    item = _require_mapping(value, f"aliases[{index}]")
    _require_exact_fields(
        item,
        required={"id", "replacement", "values"},
        context=f"aliases[{index}]",
    )
    alias_id = _require_identifier(item.get("id"), f"aliases[{index}].id", _ID_PATTERN)
    replacement = _require_text(item.get("replacement"), "replacement")
    values = tuple(_non_empty_texts(item.get("values"), "values"))
    for original in values:
        if len(_normalized_identifier(original)) < MIN_ALIAS_VALUE_LENGTH:
            raise ValueError("Valores de alias precisam ter ao menos quatro caracteres.")
        if _normalized_identifier(original) in _normalized_identifier(replacement):
            raise ValueError("replacement nao pode conter o identificador original.")
    return AliasRule(alias_id, replacement, values)


def _remove_annotations(page: fitz.Page) -> int:
    annotations = list(page.annots() or [])
    for annotation in annotations:
        page.delete_annot(annotation)
    return len(annotations)


def _remove_widgets(page: fitz.Page) -> int:
    widgets = list(page.widgets() or [])
    for widget in widgets:
        page.delete_widget(widget)
    return len(widgets)


def _remove_embedded_files(document: fitz.Document) -> int:
    names = list(document.embfile_names())
    for name in names:
        document.embfile_del(name)
    return len(names)


def _clear_pdf_metadata(document: fitz.Document) -> None:
    document.set_metadata({key: "" for key in document.metadata})
    delete_xml_metadata = getattr(document, "del_xml_metadata", None)
    if callable(delete_xml_metadata):
        delete_xml_metadata()


def _counts_to_list(values: dict[tuple[str, int], int]) -> list[dict[str, object]]:
    return [
        {"category": category, "page": page, "count": count}
        for (category, page), count in sorted(values.items())
    ]


def _alias_counts_to_list(values: dict[tuple[str, int], int]) -> list[dict[str, object]]:
    return [
        {"alias_id": alias_id, "page": page, "count": count}
        for (alias_id, page), count in sorted(values.items())
    ]


def _ensure_no_direct_identifiers(
    values: list[str],
    aliases: tuple[AliasRule, ...],
) -> None:
    text = "\n".join(values)
    categories = [
        identifier.category
        for identifier in IDENTIFIER_PATTERNS
        if identifier.regex.search(text)
    ]
    if categories:
        raise ValueError(
            "A ficha contem identificadores diretos: " + ", ".join(sorted(categories))
        )
    normalized_text = _normalized_identifier(text)
    leaked_aliases = sorted(
        {
            alias.id
            for alias in aliases
            for value in alias.values
            if _normalized_identifier(value) in normalized_text
        }
    )
    if leaked_aliases:
        raise ValueError(
            "A ficha contem aliases originais: " + ", ".join(leaked_aliases)
        )


def _positive_sorted_ints(value: object, field: str) -> list[int]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} deve ser uma lista nao vazia")
    if not all(isinstance(item, int) and not isinstance(item, bool) and item > 0 for item in value):
        raise ValueError(f"{field} deve conter paginas positivas")
    if value != sorted(set(value)):
        raise ValueError(f"{field} deve estar ordenado e sem duplicatas")
    return value


def _ensure_pages_exist(
    pages: list[int],
    page_count: int,
    question_id: str,
    field: str,
) -> None:
    invalid = [page for page in pages if page > page_count]
    if invalid:
        raise ValueError(
            f"A pergunta {question_id} cita pagina inexistente em {field}: "
            + ", ".join(str(page) for page in invalid)
        )


def _non_empty_texts(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} deve ser uma lista nao vazia")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{field} deve conter textos nao vazios")
    normalized = [item.strip() for item in value]
    if len({_normalized_identifier(item) for item in normalized}) != len(normalized):
        raise ValueError(f"{field} nao pode conter duplicatas")
    return normalized


def _require_list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{field} deve ser uma lista")
    return value


def _require_mapping(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} deve ser um objeto")
    return value


def _load_mapping(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _require_mapping(payload, "raiz")


def _require_exact_fields(
    payload: dict[str, Any],
    *,
    required: set[str],
    context: str,
) -> None:
    missing = required - set(payload)
    unknown = set(payload) - required
    if missing:
        raise ValueError(f"Campos obrigatorios ausentes em {context}: {', '.join(sorted(missing))}")
    if unknown:
        raise ValueError(f"Campos desconhecidos em {context}: {', '.join(sorted(unknown))}")


def _require_identifier(value: object, field: str, pattern: re.Pattern[str]) -> str:
    text = _require_text(value, field)
    if not pattern.fullmatch(text):
        raise ValueError(f"{field} possui formato invalido")
    return text


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} deve ser texto nao vazio")
    return value.strip()


def _ensure_unique(values, field: str) -> None:
    items = list(values)
    if len(items) != len(set(items)):
        raise ValueError(f"{field} nao pode conter duplicatas")


def _casefold_count(text: str, value: str) -> int:
    return text.casefold().count(value.casefold())


def _normalized_identifier(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return "".join(character for character in without_accents if character.isalnum())


def _file_sha256(path: Path) -> str:
    return _bytes_sha256(path.read_bytes())


def _bytes_sha256(content: bytes) -> str:
    return sha256(content).hexdigest()


def _write_json(payload: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()
