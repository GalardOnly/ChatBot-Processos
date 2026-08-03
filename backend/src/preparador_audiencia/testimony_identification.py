from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

IdentificationMethod = Literal[
    "rotulo_cabecalho",
    "titulo_nominal",
    "qualificacao",
    "nao_identificado",
]
IdentificationConfidence = Literal["alta", "media", "baixa"]

_NAME = r"[A-ZÀ-ÖØ-Ý][A-ZÀ-ÖØ-Ýa-zà-öø-ÿ .\r\n'-]{3,160}?"
_QUALIFICATION_MARKERS = (
    r"nacionalidade",
    r"naturalidade",
    r"brasileir[oa]",
    r"estado\s+civil",
    r"profiss[aã]o",
    r"residente",
    r"filh[oa]",
    r"nascid[oa]",
    r"rg",
    r"cpf",
)
_TERMINATOR = (
    r"(?=\s*(?:(?:,|;)\s*(?:"
    + "|".join(_QUALIFICATION_MARKERS)
    + r")|\n\s*(?:"
    + "|".join(_QUALIFICATION_MARKERS)
    + r")|(?:\d{1,3}\s*)?inqu[eé]rito|$))"
)
_ROLE_LABELS = {
    "vitima": r"(?:a\s+)?(?:v[ií]tima|ofendid[oa]|lesad[oa])",
    "testemunha": r"(?:a\s+)?testemunha",
    "condutor": r"(?:o\s+)?condutor",
    "reu": r"(?:o\s+)?(?:infrator|interrogado|autuado|acusado|indiciado|investigado|r[eé]u)",
    "declarante": r"(?:o|a)?\s*declarante",
    "informante": r"(?:o|a)?\s*informante",
}
_REJECTED_NAMES = {
    "naoinformado",
    "naoconsta",
    "testemunha",
    "vitima",
    "condutor",
    "declarante",
    "interrogado",
    "infrator",
}


@dataclass(frozen=True)
class TestimonyIdentification:
    name: str | None
    normalized_name: str | None
    method: IdentificationMethod
    confidence: IdentificationConfidence
    evidence: str | None
    page_number: int | None

    @property
    def status(self) -> str:
        return "identificado" if self.name else "nao_identificado"


def identify_testimony_person(
    pages: list[tuple[int, str]],
    role: str,
) -> TestimonyIdentification:
    label = _ROLE_LABELS.get(role)
    if label is not None:
        separator = r"(?:\s*[(（]\s*a\s*[)）])?\s*(?::|-)\s*"
        if role == "reu":
            separator = r"(?:\s*[(（]\s*a\s*[)）])?\s*(?:(?::|-)\s*|\s+)"
        result = _find_with_pattern(
            pages,
            rf"{label}{separator}(?P<name>{_NAME}){_TERMINATOR}",
            method="rotulo_cabecalho",
            confidence="alta",
        )
        if result is not None:
            return result

    title_patterns = _title_patterns_for_role(role)
    for pattern in title_patterns:
        result = _find_with_pattern(
            pages,
            pattern,
            method="titulo_nominal",
            confidence="alta",
        )
        if result is not None:
            return result

    if role == "declarante":
        result = _find_with_pattern(
            pages,
            rf"compareceu\s+(?:em\s+)?cart[oó]rio\s+(?P<name>{_NAME}){_TERMINATOR}",
            method="qualificacao",
            confidence="media",
        )
        if result is not None:
            return result

    return TestimonyIdentification(
        name=None,
        normalized_name=None,
        method="nao_identificado",
        confidence="baixa",
        evidence=None,
        page_number=None,
    )


def _title_patterns_for_role(role: str) -> tuple[str, ...]:
    if role == "declarante":
        return (
            rf"termo\s+de\s+declara(?:ç[aã]o|cao|ç[oõ]es|coes)\s+de\s+"
            rf"(?P<name>{_NAME}){_TERMINATOR}",
        )
    if role in {"testemunha", "informante", "vitima"}:
        return (
            rf"termo\s+de\s+(?:depoimento|oitiva)\s+de\s+"
            rf"(?P<name>{_NAME}){_TERMINATOR}",
        )
    if role == "reu":
        return (
            rf"termo\s+de\s+interrogat[oó]rio\s+de\s+"
            rf"(?P<name>{_NAME}){_TERMINATOR}",
        )
    return ()


def _find_with_pattern(
    pages: list[tuple[int, str]],
    pattern: str,
    *,
    method: IdentificationMethod,
    confidence: IdentificationConfidence,
) -> TestimonyIdentification | None:
    compiled = re.compile(pattern, re.IGNORECASE)
    for page_number, text in pages:
        for match in compiled.finditer(text[:5000]):
            name = _clean_name(match.group("name"))
            if name is None:
                continue
            return TestimonyIdentification(
                name=name,
                normalized_name=normalize_person_name(name),
                method=method,
                confidence=confidence,
                evidence=_evidence(match.group(0)),
                page_number=page_number,
            )
    return None


def normalize_person_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", without_marks).strip().upper()


def _clean_name(value: str) -> str | None:
    candidate = re.sub(r"\s+", " ", value).strip(" .,:;-()")
    words = candidate.split()
    if not 2 <= len(words) <= 12:
        return None
    if not all(any(char.isalpha() for char in word) for word in words):
        return None
    compact = _compact(candidate)
    if compact in _REJECTED_NAMES:
        return None
    if _compact(words[0]) in _REJECTED_NAMES:
        return None
    if any(
        marker in compact
        for marker in ("inquerito", "nacionalidade", "naturalidade", "disseque")
    ):
        return None
    return candidate


def _evidence(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()[:240]


def _compact(value: str) -> str:
    return "".join(char.lower() for char in normalize_person_name(value) if char.isalnum())
