from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

SCHEMA_VERSION = "1.0"
REVIEW_STATUSES = frozenset({"pending", "in_review", "approved", "rejected"})

_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_DOMAIN_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


@dataclass(frozen=True)
class ReferenceCase:
    id: str
    pergunta: str
    expected_pages: list[int]
    expected_terms: list[str]
    response_relevant_pages: list[int] | None = None
    response_expected_terms: list[str] | None = None
    review_status: str = "pending"
    reviewer: str | None = None
    review_notes: str = ""

    REQUIRED_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"id", "pergunta", "expected_pages", "expected_terms"}
    )
    OPTIONAL_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "response_relevant_pages",
            "response_expected_terms",
            "review_status",
            "reviewer",
            "review_notes",
        }
    )

    def __post_init__(self) -> None:
        _validate_id(self.id, "caso")
        _validate_non_empty_string(self.pergunta, "pergunta")
        _validate_pages(self.expected_pages)
        _validate_terms(self.expected_terms)
        if self.response_relevant_pages is not None:
            _validate_pages(
                self.response_relevant_pages,
                field="response_relevant_pages",
            )
        if self.response_expected_terms is not None:
            _validate_terms(
                self.response_expected_terms,
                field="response_expected_terms",
            )
        _validate_review(self.review_status, self.reviewer, self.review_notes)

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "id": self.id,
            "pergunta": self.pergunta,
            "expected_pages": list(self.expected_pages),
            "expected_terms": list(self.expected_terms),
            "response_relevant_pages": (
                list(self.response_relevant_pages)
                if self.response_relevant_pages is not None
                else None
            ),
            "response_expected_terms": (
                list(self.response_expected_terms)
                if self.response_expected_terms is not None
                else None
            ),
            "review_status": self.review_status,
            "reviewer": self.reviewer,
            "review_notes": self.review_notes,
        }

    def validate(self) -> None:
        self.__post_init__()

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ReferenceCase:
        _validate_fields(
            payload,
            required=cls.REQUIRED_FIELDS,
            optional=cls.OPTIONAL_FIELDS,
            context="caso",
        )
        return cls(
            id=_require_string(payload, "id", "caso"),
            pergunta=_require_string(payload, "pergunta", "caso"),
            expected_pages=_require_int_list(payload, "expected_pages", "caso"),
            expected_terms=_require_string_list(payload, "expected_terms", "caso"),
            response_relevant_pages=_optional_int_list(
                payload, "response_relevant_pages", "caso"
            ),
            response_expected_terms=_optional_string_list(
                payload, "response_expected_terms", "caso"
            ),
            review_status=_optional_string(payload, "review_status", "pending", "caso"),
            reviewer=_optional_nullable_string(payload, "reviewer", "caso"),
            review_notes=_optional_string(payload, "review_notes", "", "caso"),
        )


@dataclass(frozen=True)
class ReferenceProcess:
    id: str
    domain: str
    document: str
    cases: list[ReferenceCase]
    source: str | None = None
    source_url: str | None = None
    sha256: str | None = None
    text_sha256: str | None = None

    REQUIRED_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"id", "domain", "document", "cases"}
    )
    OPTIONAL_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"source", "source_url", "sha256", "text_sha256"}
    )

    def __post_init__(self) -> None:
        _validate_id(self.id, "processo")
        _validate_domain(self.domain)
        _validate_document(self.document)
        _validate_optional_string(self.source, "source")
        _validate_optional_string(self.source_url, "source_url")
        _validate_sha256(self.sha256)
        _validate_sha256(self.text_sha256, field="text_sha256")
        if not isinstance(self.cases, list) or not self.cases:
            raise ValueError("processo.cases deve ser uma lista nao vazia")
        if not all(isinstance(case, ReferenceCase) for case in self.cases):
            raise ValueError("processo.cases deve conter apenas casos de referencia")
        _validate_unique_ids(self.cases, "caso")

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "id": self.id,
            "domain": self.domain,
            "document": self.document,
            "source": self.source,
            "source_url": self.source_url,
            "sha256": self.sha256,
            "text_sha256": self.text_sha256,
            "cases": [case.to_dict() for case in self.cases],
        }

    def validate(self) -> None:
        self.__post_init__()
        for case in self.cases:
            case.validate()

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ReferenceProcess:
        _validate_fields(
            payload,
            required=cls.REQUIRED_FIELDS,
            optional=cls.OPTIONAL_FIELDS,
            context="processo",
        )
        cases_payload = _require_list(payload, "cases", "processo")
        return cls(
            id=_require_string(payload, "id", "processo"),
            domain=_require_string(payload, "domain", "processo"),
            document=_require_string(payload, "document", "processo"),
            source=_optional_nullable_string(payload, "source", "processo"),
            source_url=_optional_nullable_string(payload, "source_url", "processo"),
            sha256=_optional_nullable_string(payload, "sha256", "processo"),
            text_sha256=_optional_nullable_string(
                payload, "text_sha256", "processo"
            ),
            cases=[
                ReferenceCase.from_dict(_require_mapping(item, f"processo.cases[{index}]"))
                for index, item in enumerate(cases_payload)
            ],
        )


@dataclass(frozen=True)
class ReferenceSuite:
    id: str
    processes: list[ReferenceProcess]
    description: str = ""
    schema_version: str = SCHEMA_VERSION

    REQUIRED_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"schema_version", "id", "processes"}
    )
    OPTIONAL_FIELDS: ClassVar[frozenset[str]] = frozenset({"description"})

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"schema_version deve ser {SCHEMA_VERSION!r}; recebido {self.schema_version!r}"
            )
        _validate_id(self.id, "suite")
        if not isinstance(self.description, str):
            raise ValueError("description deve ser texto")
        if not isinstance(self.processes, list) or not self.processes:
            raise ValueError("processes deve ser uma lista nao vazia")
        if not all(isinstance(process, ReferenceProcess) for process in self.processes):
            raise ValueError("processes deve conter apenas processos de referencia")
        _validate_unique_ids(self.processes, "processo")

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "description": self.description,
            "processes": [process.to_dict() for process in self.processes],
        }

    def validate(self) -> None:
        self.__post_init__()
        for process in self.processes:
            process.validate()

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ReferenceSuite:
        _validate_fields(
            payload,
            required=cls.REQUIRED_FIELDS,
            optional=cls.OPTIONAL_FIELDS,
            context="suite",
        )
        processes_payload = _require_list(payload, "processes", "suite")
        return cls(
            schema_version=_require_string(payload, "schema_version", "suite"),
            id=_require_string(payload, "id", "suite"),
            description=_optional_string(payload, "description", "", "suite"),
            processes=[
                ReferenceProcess.from_dict(
                    _require_mapping(item, f"suite.processes[{index}]")
                )
                for index, item in enumerate(processes_payload)
            ],
        )


def load_reference_suite(path: str | Path) -> ReferenceSuite:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return ReferenceSuite.from_dict(_require_mapping(payload, "raiz"))


def write_reference_suite(suite: ReferenceSuite, path: str | Path) -> None:
    if not isinstance(suite, ReferenceSuite):
        raise TypeError("suite deve ser uma ReferenceSuite")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(suite.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _validate_id(value: object, context: str) -> None:
    if not isinstance(value, str) or not _ID_PATTERN.fullmatch(value):
        raise ValueError(
            f"{context}.id deve usar apenas letras minusculas, numeros, ponto, "
            "hifen ou sublinhado"
        )


def _validate_domain(value: object) -> None:
    if not isinstance(value, str) or not _DOMAIN_PATTERN.fullmatch(value):
        raise ValueError(
            "processo.domain deve usar apenas letras minusculas, numeros, ponto, "
            "hifen ou sublinhado"
        )


def _validate_document(value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("processo.document deve ser texto nao vazio")
    path = Path(value)
    if path.name != value or path.suffix.lower() != ".pdf":
        raise ValueError("processo.document deve ser apenas o nome de um arquivo PDF")


def _validate_sha256(value: object, *, field: str = "sha256") -> None:
    if value is None:
        return
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError(
            f"processo.{field} deve ser um hash hexadecimal de 64 caracteres"
        )


def _validate_non_empty_string(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} deve ser texto nao vazio")


def _validate_optional_string(value: object, field: str) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ValueError(f"{field} deve ser nulo ou texto nao vazio")


def _validate_pages(pages: object, *, field: str = "expected_pages") -> None:
    if not isinstance(pages, list) or not pages:
        raise ValueError(f"{field} deve ser uma lista nao vazia")
    if any(isinstance(page, bool) or not isinstance(page, int) or page <= 0 for page in pages):
        raise ValueError(f"{field} deve conter apenas inteiros positivos")
    if pages != sorted(set(pages)):
        raise ValueError(f"{field} deve estar em ordem crescente e sem duplicatas")


def _validate_terms(terms: object, *, field: str = "expected_terms") -> None:
    if not isinstance(terms, list) or not terms:
        raise ValueError(f"{field} deve ser uma lista nao vazia")
    if any(not isinstance(term, str) or not term.strip() for term in terms):
        raise ValueError(f"{field} deve conter apenas textos nao vazios")
    normalized = [term.strip().casefold() for term in terms]
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field} nao pode conter duplicatas")


def _validate_review(status: object, reviewer: object, notes: object) -> None:
    if not isinstance(status, str) or status not in REVIEW_STATUSES:
        allowed = ", ".join(sorted(REVIEW_STATUSES))
        raise ValueError(f"review_status invalido; use um de: {allowed}")
    _validate_optional_string(reviewer, "reviewer")
    if not isinstance(notes, str):
        raise ValueError("review_notes deve ser texto")
    if status == "pending" and reviewer is not None:
        raise ValueError("reviewer deve ser nulo quando review_status for pending")
    if status != "pending" and reviewer is None:
        raise ValueError(f"reviewer e obrigatorio quando review_status for {status}")


def _validate_unique_ids(items: list[Any], context: str) -> None:
    ids = [item.id for item in items]
    duplicates = sorted({item_id for item_id in ids if ids.count(item_id) > 1})
    if duplicates:
        raise ValueError(f"{context}.id duplicado: {', '.join(duplicates)}")


def _validate_fields(
    payload: dict[str, Any],
    *,
    required: frozenset[str],
    optional: frozenset[str],
    context: str,
) -> None:
    missing = sorted(required - payload.keys())
    if missing:
        raise ValueError(f"{context} sem campos obrigatorios: {', '.join(missing)}")
    unexpected = sorted(payload.keys() - required - optional)
    if unexpected:
        raise ValueError(f"{context} contem campos desconhecidos: {', '.join(unexpected)}")


def _require_mapping(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} deve ser um objeto JSON")
    return value


def _require_list(payload: dict[str, Any], field: str, context: str) -> list[Any]:
    value = payload[field]
    if not isinstance(value, list):
        raise ValueError(f"{context}.{field} deve ser uma lista")
    return value


def _require_string(payload: dict[str, Any], field: str, context: str) -> str:
    value = payload[field]
    if not isinstance(value, str):
        raise ValueError(f"{context}.{field} deve ser texto")
    return value


def _optional_string(
    payload: dict[str, Any],
    field: str,
    default: str,
    context: str,
) -> str:
    if field not in payload:
        return default
    return _require_string(payload, field, context)


def _optional_nullable_string(
    payload: dict[str, Any],
    field: str,
    context: str,
) -> str | None:
    value = payload.get(field)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{context}.{field} deve ser nulo ou texto")
    return value


def _require_int_list(payload: dict[str, Any], field: str, context: str) -> list[int]:
    values = _require_list(payload, field, context)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise ValueError(f"{context}.{field} deve conter apenas inteiros")
    return values


def _optional_int_list(
    payload: dict[str, Any],
    field: str,
    context: str,
) -> list[int] | None:
    if payload.get(field) is None:
        return None
    return _require_int_list(payload, field, context)


def _require_string_list(payload: dict[str, Any], field: str, context: str) -> list[str]:
    values = _require_list(payload, field, context)
    if any(not isinstance(value, str) for value in values):
        raise ValueError(f"{context}.{field} deve conter apenas textos")
    return values


def _optional_string_list(
    payload: dict[str, Any],
    field: str,
    context: str,
) -> list[str] | None:
    if payload.get(field) is None:
        return None
    return _require_string_list(payload, field, context)
