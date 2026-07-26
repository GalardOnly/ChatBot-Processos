from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from preparador_audiencia.search import SearchResult

PAGE_CITATION_PATTERN = re.compile(
    r"(?:\[?\s*(?:p|pag|pagina)\.?\s*(\d+)\s*\]?)",
    flags=re.IGNORECASE,
)
UNCERTAINTY_MARKERS = [
    "nao consta",
    "nao ha base",
    "nao foi encontrado",
    "precisa ser confirmado",
    "precisa ser confirmada",
    "precisa confirmar",
    "deve ser confirmado",
    "deve ser confirmada",
    "as fontes indicam",
    "os trechos indicam",
    "ponto de conferencia",
]


@dataclass(frozen=True)
class GroundingSignals:
    source_pages: list[int]
    cited_pages: list[int]
    unsupported_cited_pages: list[int]
    claim_lines: int
    cited_claim_lines: int
    uncited_claim_lines: int
    citation_coverage: float
    uncertainty_markers: int
    no_source_answer: bool
    rule_risk: str
    notes: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def inspect_response_grounding(resposta: str, sources: list[SearchResult]) -> GroundingSignals:
    source_pages = sorted({source.page_number for source in sources})
    cited_pages = _extract_cited_pages(resposta)
    unsupported = [page for page in cited_pages if page not in set(source_pages)]
    claim_lines = _claim_lines(resposta)
    cited_claim_lines = [line for line in claim_lines if PAGE_CITATION_PATTERN.search(line)]
    uncertainty_count = _count_uncertainty_markers(resposta)
    no_source_answer = _is_no_source_answer(resposta)
    citation_coverage = (
        round(len(cited_claim_lines) / len(claim_lines), 4) if claim_lines else 0.0
    )
    notes = _notes(
        source_pages=source_pages,
        unsupported=unsupported,
        claim_lines=len(claim_lines),
        citation_coverage=citation_coverage,
        uncertainty_count=uncertainty_count,
        no_source_answer=no_source_answer,
    )
    return GroundingSignals(
        source_pages=source_pages,
        cited_pages=cited_pages,
        unsupported_cited_pages=unsupported,
        claim_lines=len(claim_lines),
        cited_claim_lines=len(cited_claim_lines),
        uncited_claim_lines=len(claim_lines) - len(cited_claim_lines),
        citation_coverage=citation_coverage,
        uncertainty_markers=uncertainty_count,
        no_source_answer=no_source_answer,
        rule_risk=_rule_risk(unsupported, len(claim_lines), citation_coverage, no_source_answer),
        notes=notes,
    )


def _extract_cited_pages(text: str) -> list[int]:
    pages = {int(match.group(1)) for match in PAGE_CITATION_PATTERN.finditer(text)}
    return sorted(pages)


def _claim_lines(text: str) -> list[str]:
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        normalized = re.sub(r"^[*\-\d.\s]+", "", line).strip()
        if len(normalized) < 45:
            continue
        if not re.search(r"[A-Za-z]", normalized):
            continue
        lines.append(normalized)
    return lines


def _count_uncertainty_markers(text: str) -> int:
    normalized = text.lower()
    return sum(normalized.count(marker) for marker in UNCERTAINTY_MARKERS)


def _is_no_source_answer(text: str) -> bool:
    normalized = text.lower()
    return "nao encontrei base suficiente" in normalized or "nao ha base suficiente" in normalized


def _rule_risk(
    unsupported: list[int],
    claim_lines: int,
    citation_coverage: float,
    no_source_answer: bool,
) -> str:
    if unsupported:
        return "alto"
    if no_source_answer:
        return "baixo"
    if claim_lines >= 3 and citation_coverage < 0.35:
        return "alto"
    if claim_lines >= 3 and citation_coverage < 0.65:
        return "medio"
    return "baixo"


def _notes(
    *,
    source_pages: list[int],
    unsupported: list[int],
    claim_lines: int,
    citation_coverage: float,
    uncertainty_count: int,
    no_source_answer: bool,
) -> list[str]:
    notes = []
    if not source_pages and not no_source_answer:
        notes.append("resposta sem fontes recuperadas")
    if unsupported:
        notes.append("citou pagina que nao veio das fontes recuperadas")
    if claim_lines >= 3 and citation_coverage < 0.65:
        notes.append("muitas linhas afirmativas sem citacao de pagina")
    if uncertainty_count:
        notes.append("usa linguagem de cautela ou confirma lacunas")
    if no_source_answer:
        notes.append("resposta declarou falta de base suficiente")
    return notes
