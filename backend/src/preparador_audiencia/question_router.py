from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

from preparador_audiencia.question_bank import QuestionTemplate, list_question_templates
from preparador_audiencia.question_sources import (
    QuestionCandidate,
    generate_question_candidates,
    load_question_sources,
)

MIN_TOKEN_LENGTH = 3
DEFAULT_GUIDE_LIMIT = 4


@dataclass(frozen=True)
class QuestionGuide:
    id: str
    titulo: str
    area: str
    audiencia: str
    objetivo: str
    pergunta: str
    tags: list[str]
    source: str
    score: float


@dataclass(frozen=True)
class QuestionRoute:
    pergunta_original: str
    area: str | None
    audiencia: str | None
    guides: list[QuestionGuide]

    def search_query(self) -> str:
        guide_terms = " ".join(guide.titulo for guide in self.guides[:2])
        return f"{self.pergunta_original} {guide_terms}".strip()

    def llm_question(self) -> str:
        if not self.guides:
            return self.pergunta_original
        return "\n\n".join(
            [
                f"Pergunta original do defensor:\n{self.pergunta_original}",
                (
                    "Triagem interna: use as perguntas-guia abaixo apenas para entender "
                    "a intencao e organizar melhor a resposta. Nao mencione esta triagem "
                    "ao usuario."
                ),
                _guides_block(self.guides),
                (
                    "Responda a pergunta original de forma natural, pratica e focada na "
                    "preparacao de audiencia. Use as fontes do processo para sustentar "
                    "cada ponto e cite paginas."
                ),
            ]
        )


def route_question(pergunta: str, *, limit: int = DEFAULT_GUIDE_LIMIT) -> QuestionRoute:
    guides = rank_question_guides(pergunta, limit=limit)
    return QuestionRoute(
        pergunta_original=pergunta,
        area=guides[0].area if guides else None,
        audiencia=guides[0].audiencia if guides else None,
        guides=guides,
    )


def rank_question_guides(pergunta: str, *, limit: int = DEFAULT_GUIDE_LIMIT) -> list[QuestionGuide]:
    query_tokens = _tokens(pergunta)
    if not query_tokens:
        return []
    scored = [
        guide
        for template in _load_guides()
        if (guide := _score_guide(template, query_tokens)).score > 0
    ]
    scored.sort(key=lambda guide: (guide.score, guide.source == "oficial"), reverse=True)
    return scored[:limit]


@lru_cache(maxsize=1)
def _load_guides() -> tuple[QuestionGuide, ...]:
    official = [
        _guide_from_template(template)
        for template in list_question_templates()
    ]
    candidates = [
        _guide_from_candidate(candidate)
        for candidate in generate_question_candidates(load_question_sources(), official_only=True)
    ]
    return tuple(official + candidates)


def _score_guide(template: QuestionGuide, query_tokens: set[str]) -> QuestionGuide:
    haystack = " ".join(
        [
            template.titulo,
            template.area,
            template.audiencia,
            template.objetivo,
            template.pergunta,
            " ".join(template.tags),
        ]
    )
    guide_tokens = _tokens(haystack)
    overlap = query_tokens.intersection(guide_tokens)
    if not overlap:
        return QuestionGuide(**{**template.__dict__, "score": 0.0})
    coverage = len(overlap) / max(1, len(query_tokens))
    specificity = len(overlap) / max(1, len(guide_tokens))
    score = round((0.75 * coverage) + (0.25 * specificity), 4)
    if template.source == "oficial":
        score += 0.05
    return QuestionGuide(**{**template.__dict__, "score": score})


def _guide_from_template(template: QuestionTemplate) -> QuestionGuide:
    return QuestionGuide(
        id=template.id,
        titulo=template.titulo,
        area=template.area,
        audiencia=template.audiencia,
        objetivo=template.objetivo,
        pergunta=template.pergunta,
        tags=template.tags,
        source="oficial",
        score=0.0,
    )


def _guide_from_candidate(candidate: QuestionCandidate) -> QuestionGuide:
    return QuestionGuide(
        id=candidate.id,
        titulo=candidate.titulo,
        area=candidate.area,
        audiencia=candidate.audiencia,
        objetivo=candidate.objetivo,
        pergunta=candidate.pergunta,
        tags=candidate.tags,
        source="candidata",
        score=0.0,
    )


def _guides_block(guides: list[QuestionGuide]) -> str:
    lines = ["Perguntas-guia ranqueadas:"]
    for index, guide in enumerate(guides, start=1):
        lines.extend(
            [
                f"{index}. Area: {guide.area}; audiencia: {guide.audiencia}; "
                f"origem: {guide.source}; score: {guide.score:.2f}",
                f"Objetivo: {guide.objetivo}",
                f"Pergunta-guia: {guide.pergunta}",
            ]
        )
    return "\n".join(lines)


def _tokens(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", text.lower())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return {
        token
        for token in re.findall(r"[a-z0-9_]+", normalized)
        if len(token) >= MIN_TOKEN_LENGTH
    }
