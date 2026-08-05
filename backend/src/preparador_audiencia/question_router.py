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
MIN_GUIDE_SCORE = 0.36
TOKEN_ALIASES = {
    "beneficiaria": "beneficiario",
    "julgado": "julgamento",
    "julgou": "julgamento",
    "recursos": "recurso",
}
GUIDE_REQUIRED_ANY = {
    "geral_identificacao_julgamento": {
        "identificacao",
        "numero",
        "recurso",
        "relator",
    },
    "geral_resultado_julgamento": {
        "decidiu",
        "decisao",
        "provimento",
        "resultado",
    },
}
ROUTING_STOPWORDS = {
    "antes",
    "ainda",
    "algum",
    "alguma",
    "algumas",
    "alguns",
    "aparece",
    "aparecem",
    "audiencia",
    "caso",
    "como",
    "confirmar",
    "contexto",
    "deve",
    "devem",
    "deveria",
    "disso",
    "dizer",
    "documento",
    "durante",
    "ele",
    "ela",
    "esse",
    "esta",
    "este",
    "fazer",
    "feito",
    "foi",
    "informa",
    "informacoes",
    "isso",
    "neste",
    "onde",
    "para",
    "pela",
    "pelo",
    "pode",
    "poderia",
    "pontos",
    "porque",
    "processo",
    "qual",
    "quais",
    "quando",
    "quem",
    "sobre",
    "ser",
    "tem",
    "ter",
    "uma",
    "voce",
    "que",
}


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

    def guide_query(self) -> str:
        return " ".join(
            " ".join(
                [
                    guide.titulo,
                    guide.objetivo,
                    " ".join(tag.replace("_", " ") for tag in guide.tags),
                ]
            )
            for guide in self.guides[:2]
        )

    def search_query(self) -> str:
        guide_terms = self.guide_query()
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
    ranked_guides = rank_question_guides(pergunta, limit=limit)
    guides = [guide for guide in ranked_guides if guide.score >= MIN_GUIDE_SCORE]
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
    return _distinct_guides(scored, limit)


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
    required_tokens = GUIDE_REQUIRED_ANY.get(template.id)
    if required_tokens and not query_tokens.intersection(required_tokens):
        return QuestionGuide(**{**template.__dict__, "score": 0.0})
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
    if len(query_tokens) > 1 and len(overlap) < 2:
        return QuestionGuide(**{**template.__dict__, "score": 0.0})
    coverage = len(overlap) / max(1, len(query_tokens))
    specificity = len(overlap) / max(1, len(guide_tokens))
    title_tokens = _tokens(template.titulo.split(" - ", 1)[0])
    exact_topic_bonus = (
        0.2
        if len(title_tokens) >= 2 and title_tokens.issubset(query_tokens)
        else 0.0
    )
    score = round((0.75 * coverage) + (0.25 * specificity) + exact_topic_bonus, 4)
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


def _distinct_guides(
    guides: list[QuestionGuide],
    limit: int,
) -> list[QuestionGuide]:
    selected = []
    topics: set[str] = set()
    for guide in guides:
        topic = _normalize_topic(guide.titulo.split(" - ", 1)[0])
        if topic in topics:
            continue
        topics.add(topic)
        selected.append(guide)
        if len(selected) >= limit:
            break
    return selected


def _normalize_topic(text: str) -> str:
    return " ".join(sorted(_tokens(text)))


def _tokens(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", text.lower().replace("_", " "))
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return {
        TOKEN_ALIASES.get(token, token)
        for token in re.findall(r"[a-z0-9_]+", normalized)
        if len(token) >= MIN_TOKEN_LENGTH and token not in ROUTING_STOPWORDS
    }
