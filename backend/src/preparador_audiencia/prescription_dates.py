from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from preparador_audiencia.repositories import ChunkRecord

_DATE_EXPRESSION = (
    r"(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
    r"\d{1,2}\s+de\s+[A-Za-z\u00c0-\u00ff]+\s+de\s+\d{4})"
)
_DATE_PATTERN = re.compile(_DATE_EXPRESSION, re.IGNORECASE)
_ARTICLE_PATTERN = re.compile(
    r"\bart(?:igo)?\.?\s*\d{1,4}(?:-[A-Z])?"
    r"(?:\s*,?\s*(?:caput|\u00a7{1,2}\s*\d+[A-Za-z]?|inciso\s+[IVXLCDM]+))*",
    re.IGNORECASE,
)
_PENALTY_PATTERN = re.compile(
    r"pena\s*[-:]?\s*(?:reclusao|detencao)?\s*,?\s*de\s+"
    r"(?P<minimum>\d{1,2})(?:\s*\([^)]*\))?\s+a\s+"
    r"(?P<maximum>\d{1,2})(?:\s*\([^)]*\))?\s+anos?",
    re.IGNORECASE,
)

_EVENT_RULES = (
    (
        "nascimento_reu",
        "Data de nascimento do reu",
        re.compile(r"\b(?:nascid[oa]|data\s+de\s+nascimento)\b", re.IGNORECASE),
        "pessoal",
    ),
    (
        "recebimento_denuncia",
        "Recebimento da denuncia ou queixa",
        re.compile(
            r"\b(?:recebo|recebida|recebimento)\b.{0,40}\b(?:denuncia|queixa)\b|"
            r"\b(?:denuncia|queixa)\b.{0,40}\b(?:recebida|recebimento)\b",
            re.IGNORECASE | re.DOTALL,
        ),
        "interruptivo",
    ),
    (
        "confirmacao_pronuncia",
        "Decisao confirmatoria da pronuncia",
        re.compile(r"\b(?:confirmo|confirmada)\b.{0,50}\bpronuncia\b", re.IGNORECASE),
        "interruptivo",
    ),
    (
        "pronuncia",
        "Pronuncia",
        re.compile(
            r"\b(?:pronuncio\s+o\s+acusado|sentenca\s+de\s+pronuncia|"
            r"decisao\s+de\s+pronuncia)\b",
            re.IGNORECASE,
        ),
        "interruptivo",
    ),
    (
        "acordao_condenatorio",
        "Acordao condenatorio recorrivel",
        re.compile(r"\bacordao\b.{0,45}\bcondenatorio\b", re.IGNORECASE | re.DOTALL),
        "interruptivo",
    ),
    (
        "sentenca_condenatoria",
        "Sentenca condenatoria recorrivel",
        re.compile(r"\bsentenca\b.{0,45}\bcondenatori[ao]\b", re.IGNORECASE | re.DOTALL),
        "interruptivo",
    ),
    (
        "suspensao_inicio",
        "Inicio de suspensao do prazo",
        re.compile(
            r"\b(?:suspendo|suspensao|suspenso)\b.{0,90}"
            r"\b(?:processo|prazo\s+prescricional|art\.?\s*366)\b",
            re.IGNORECASE | re.DOTALL,
        ),
        "suspensivo",
    ),
    (
        "suspensao_fim",
        "Fim de suspensao do prazo",
        re.compile(
            r"\b(?:retomo|retomada|levantada|cessada|prosseguimento)\b.{0,80}"
            r"\b(?:processo|suspensao|prazo)\b",
            re.IGNORECASE | re.DOTALL,
        ),
        "suspensivo",
    ),
    (
        "data_fato",
        "Data do fato",
        re.compile(
            r"\b(?:data\s+do\s+fato|fato\s+ocorreu|dos\s+fatos|"
            r"consta\s+do\s+incluso\s+inquerito)\b",
            re.IGNORECASE,
        ),
        "termo_inicial",
    ),
)

_MONTHS = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}


@dataclass(frozen=True)
class DateCandidate:
    id: str
    event_type: str
    label: str
    nature: str
    value: date
    raw_value: str
    page_number: int
    chunk_index: int
    excerpt: str
    source_confidence: str
    confidence: str
    review_required: bool


@dataclass(frozen=True)
class OffenseCitationCandidate:
    id: str
    article: str
    maximum_penalty_months: int | None
    page_number: int
    chunk_index: int
    excerpt: str
    source_confidence: str
    review_required: bool


@dataclass(frozen=True)
class PrescriptionDataResult:
    dates: list[DateCandidate]
    offenses: list[OffenseCitationCandidate]
    missing_fields: list[str]
    warnings: list[str]


def extract_prescription_data(chunks: list[ChunkRecord]) -> PrescriptionDataResult:
    date_candidates: list[DateCandidate] = []
    offense_candidates: list[OffenseCitationCandidate] = []
    for chunk in chunks:
        if not chunk.text.strip():
            continue
        for event_type, label, marker, nature in _EVENT_RULES:
            date_candidates.extend(
                _dates_near_markers(chunk, event_type, label, marker, nature)
            )
        offense_candidates.extend(_offense_citations(chunk))

    dates = _deduplicate_dates(date_candidates)
    offenses = _deduplicate_offenses(offense_candidates)
    found_types = {candidate.event_type for candidate in dates}
    missing_fields = []
    for event_type, label in (
        ("data_fato", "Data do fato ou outro termo inicial do art. 111 do CP"),
        ("nascimento_reu", "Data de nascimento do reu"),
        ("recebimento_denuncia", "Data do recebimento da denuncia ou queixa"),
    ):
        if event_type not in found_types:
            missing_fields.append(label)
    if not offenses:
        missing_fields.append("Delito, artigo e pena maxima aplicavel")
    warnings = [
        "Os dados sao candidatos extraidos do processo e precisam ser selecionados antes "
        "do calculo. Nenhuma data foi confirmada automaticamente."
    ]
    if any(item.source_confidence not in {"alta", "media"} for item in dates):
        warnings.append("Ha datas vindas de OCR com confianca insuficiente.")
    return PrescriptionDataResult(dates, offenses, missing_fields, warnings)


def _dates_near_markers(
    chunk: ChunkRecord,
    event_type: str,
    label: str,
    marker_pattern: re.Pattern[str],
    nature: str,
) -> list[DateCandidate]:
    found: list[DateCandidate] = []
    folded_text = _fold(chunk.text)
    for marker in marker_pattern.finditer(folded_text):
        start = max(0, marker.start() - 180)
        end = min(len(chunk.text), marker.end() + 750)
        window = chunk.text[start:end]
        date_matches = list(_DATE_PATTERN.finditer(window))
        if not date_matches:
            continue
        distances = [
            _span_distance(
                marker.start(),
                marker.end(),
                start + match.start(),
                start + match.end(),
            )
            for match in date_matches
        ]
        selected = min(
            zip(date_matches, distances, strict=True),
            key=lambda item: (
                item[1],
                0 if start + item[0].start() >= marker.end() else 1,
            ),
        )[0]
        parsed = _parse_date(selected.group(0))
        if parsed is None:
            continue
        raw_value = selected.group(0)
        absolute_date_start = start + selected.start()
        excerpt = _excerpt(chunk.text, min(marker.start(), absolute_date_start), 500)
        confidence = _candidate_confidence(chunk.source_confidence, len(date_matches))
        found.append(
            DateCandidate(
                id=_candidate_id(event_type, chunk.page_number, parsed.isoformat(), excerpt),
                event_type=event_type,
                label=label,
                nature=nature,
                value=parsed,
                raw_value=raw_value,
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
                excerpt=excerpt,
                source_confidence=chunk.source_confidence,
                confidence=confidence,
                review_required=True,
            )
        )
    return found


def _offense_citations(chunk: ChunkRecord) -> list[OffenseCitationCandidate]:
    articles = list(_ARTICLE_PATTERN.finditer(chunk.text))
    if not articles:
        return []
    penalties = list(_PENALTY_PATTERN.finditer(_fold(chunk.text)))
    found: list[OffenseCitationCandidate] = []
    for article in articles:
        excerpt = _excerpt(chunk.text, article.start(), 550)
        maximum = None
        if len(articles) == 1 and len(penalties) == 1:
            maximum = int(penalties[0].group("maximum")) * 12
        article_text = " ".join(article.group(0).split())
        found.append(
            OffenseCitationCandidate(
                id=_candidate_id("delito", chunk.page_number, article_text, excerpt),
                article=article_text,
                maximum_penalty_months=maximum,
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
                excerpt=excerpt,
                source_confidence=chunk.source_confidence,
                review_required=True,
            )
        )
    return found


def _parse_date(value: str) -> date | None:
    compact = value.strip()
    numeric = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", compact)
    if numeric:
        day, month, year = (int(item) for item in numeric.groups())
        if year < 100:
            year += 2000 if year <= 49 else 1900
        return _safe_date(year, month, day)
    textual = re.fullmatch(
        r"(\d{1,2})\s+de\s+([A-Za-z\u00c0-\u00ff]+)\s+de\s+(\d{4})",
        compact,
        re.IGNORECASE,
    )
    if textual:
        day = int(textual.group(1))
        month = _MONTHS.get(_fold(textual.group(2)))
        year = int(textual.group(3))
        return _safe_date(year, month, day) if month else None
    return None


def parse_process_date(value: str) -> date | None:
    return _parse_date(value)


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _candidate_confidence(source_confidence: str, dates_in_window: int) -> str:
    if source_confidence not in {"alta", "media"}:
        return "baixa"
    if source_confidence == "alta" and dates_in_window == 1:
        return "alta"
    return "media"


def _span_distance(
    first_start: int,
    first_end: int,
    second_start: int,
    second_end: int,
) -> int:
    if second_end < first_start:
        return first_start - second_end
    if second_start > first_end:
        return second_start - first_end
    return 0


def _deduplicate_dates(values: list[DateCandidate]) -> list[DateCandidate]:
    selected: dict[tuple[str, date], DateCandidate] = {}
    rank = {"baixa": 0, "media": 1, "alta": 2}
    for value in values:
        key = (value.event_type, value.value)
        current = selected.get(key)
        if current is None or rank[value.confidence] > rank[current.confidence]:
            selected[key] = value
    return sorted(
        selected.values(),
        key=lambda item: (item.value, item.event_type, item.page_number),
    )


def _deduplicate_offenses(
    values: list[OffenseCitationCandidate],
) -> list[OffenseCitationCandidate]:
    selected: dict[str, OffenseCitationCandidate] = {}
    for value in values:
        key = _fold(value.article)
        current = selected.get(key)
        if current is None or (
            current.maximum_penalty_months is None
            and value.maximum_penalty_months is not None
        ):
            selected[key] = value
    return sorted(selected.values(), key=lambda item: (item.page_number, item.article))


def _candidate_id(kind: str, page: int, value: str, excerpt: str) -> str:
    seed = f"{kind}|{page}|{value}|{excerpt}"
    return f"cand-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:14]}"


def _excerpt(text: str, position: int, limit: int) -> str:
    start = max(0, position - (limit // 4))
    end = min(len(text), start + limit)
    return " ".join(text[start:end].split())


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))
