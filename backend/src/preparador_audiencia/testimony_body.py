from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

BodyStatus = Literal["segmentada", "revisao_necessaria", "nao_localizada"]
BodyConfidence = Literal["alta", "media", "baixa"]

_START_PATTERNS = (
    re.compile(
        r"\b(?:DISSE|DECLAROU|INFORMOU|RELATOU|ESCLARECEU|AFIRMOU|RESPONDEU)"
        r"\s*[:,;]?\s+QUE\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:PASSOU|PASSA)\s+A\s+(?:DECLARAR|RELATAR|INFORMAR)"
        r"\s*[:,;]?\s+QUE\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:^|\n)\s*QUE\b(?!\s+(?:PRESTA|COMPARECE|FOI\s+QUALIFICAD[OA]))",
        re.IGNORECASE,
    ),
)
_END_PATTERNS = (
    re.compile(r"\bNADA\s+MAIS\s+(?:DISSE|DECLAROU|RESPONDEU)\b", re.IGNORECASE),
    re.compile(r"\bNADA\s+(?:MAIS\s+)?LHE\s+FOI\s+PERGUNTADO\b", re.IGNORECASE),
    re.compile(r"\bE\s+COMO\s+NADA\s+MAIS\b", re.IGNORECASE),
    re.compile(r"\bENCERROU-SE\s+O\s+PRESENTE\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class TestimonyBodySegment:
    page_number: int
    text: str


@dataclass(frozen=True)
class TestimonyBody:
    status: BodyStatus
    confidence: BodyConfidence
    start_marker: str | None
    end_marker: str | None
    start_page: int | None
    end_page: int | None
    segments: list[TestimonyBodySegment]
    text: str
    review_required: bool
    warnings: list[str]


def extract_testimony_body(pages: list[tuple[int, str]]) -> TestimonyBody:
    start = _find_start(pages)
    if start is None:
        return TestimonyBody(
            status="nao_localizada",
            confidence="baixa",
            start_marker=None,
            end_marker=None,
            start_page=None,
            end_page=None,
            segments=[],
            text="",
            review_required=True,
            warnings=[
                "O inicio da fala nao foi localizado com seguranca; o cabecalho e as "
                "assinaturas nao foram apresentados como depoimento."
            ],
        )

    start_index, start_offset, start_marker = start
    end = _find_end(pages, start_index, start_offset + len(start_marker))
    end_index = end[0] if end is not None else len(pages) - 1
    end_offset = end[1] if end is not None else len(pages[end_index][1])
    segments: list[TestimonyBodySegment] = []
    for index in range(start_index, end_index + 1):
        page_number, page_text = pages[index]
        left = start_offset if index == start_index else 0
        right = end_offset if index == end_index else len(page_text)
        literal = page_text[left:right].strip()
        if literal:
            segments.append(TestimonyBodySegment(page_number, literal))

    if not segments:
        return TestimonyBody(
            status="nao_localizada",
            confidence="baixa",
            start_marker=start_marker,
            end_marker=end[2] if end is not None else None,
            start_page=pages[start_index][0],
            end_page=pages[end_index][0],
            segments=[],
            text="",
            review_required=True,
            warnings=["Os marcadores foram encontrados, mas nao restou fala literal entre eles."],
        )

    if end is None:
        return TestimonyBody(
            status="revisao_necessaria",
            confidence="media",
            start_marker=start_marker,
            end_marker=None,
            start_page=pages[start_index][0],
            end_page=pages[end_index][0],
            segments=segments,
            text="\n\n".join(segment.text for segment in segments),
            review_required=True,
            warnings=[
                "O inicio da fala foi localizado, mas o encerramento formal precisa ser "
                "conferido no PDF."
            ],
        )

    return TestimonyBody(
        status="segmentada",
        confidence="alta",
        start_marker=start_marker,
        end_marker=end[2],
        start_page=pages[start_index][0],
        end_page=pages[end_index][0],
        segments=segments,
        text="\n\n".join(segment.text for segment in segments),
        review_required=False,
        warnings=[],
    )


def _find_start(pages: list[tuple[int, str]]) -> tuple[int, int, str] | None:
    for page_index, (_, text) in enumerate(pages):
        matches = [
            match
            for pattern in _START_PATTERNS
            if (match := pattern.search(text)) is not None
        ]
        if matches:
            match = min(matches, key=lambda item: item.start())
            start = match.start()
            while start < match.end() and text[start].isspace():
                start += 1
            return page_index, start, text[start : match.end()]
    return None


def _find_end(
    pages: list[tuple[int, str]],
    start_page_index: int,
    minimum_offset: int,
) -> tuple[int, int, str] | None:
    for page_index in range(start_page_index, len(pages)):
        text = pages[page_index][1]
        offset = minimum_offset if page_index == start_page_index else 0
        matches = [
            match
            for pattern in _END_PATTERNS
            if (match := pattern.search(text, offset)) is not None
        ]
        if matches:
            match = min(matches, key=lambda item: item.start())
            return page_index, match.start(), match.group(0)
    return None
