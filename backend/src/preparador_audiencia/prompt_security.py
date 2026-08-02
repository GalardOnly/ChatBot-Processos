from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from preparador_audiencia.search import SearchResult

_INJECTION_PATTERNS = {
    "ignorar_regras": re.compile(
        r"\b(ignorar|ignore|desconsiderar|desconsidere)\b.{0,50}"
        r"\b(instrucoes|regras|prompt|mensagens?)\b"
    ),
    "revelar_segredo": re.compile(
        r"\b(revelar|revele|mostrar|mostre|expor|exiba)\b.{0,50}"
        r"\b(chave|token|prompt|senha)\b"
    ),
    "mudanca_de_papel": re.compile(
        r"\b(agora voce e|atue como|finja ser|you are now|act as)\b"
    ),
    "substituicao_em_ingles": re.compile(
        r"\b(ignore|disregard)\b.{0,50}\b(instructions|rules|messages|prompt)\b"
    ),
    "marcador_de_papel": re.compile(
        r"(^|\s)#{0,3}\s*(system|assistant|developer)\s*:"
    ),
    "quebra_de_delimitador": re.compile(r"</?fonte_processual\b|feche a tag"),
    "instrucao_exclusiva_do_anexo": re.compile(
        r"\b(siga|considere|use)\s+somente\b.{0,60}"
        r"\b(orientacoes|instrucoes|regras)\b.{0,30}\b(anexo|documento|trecho)\b"
    ),
    "comando_ofuscado": re.compile(
        r"\bi\s+g\s+n\s+o\s+r\s+e\b.{0,50}\b(r\s+e\s+g\s+r\s+a\s+s)\b"
    ),
}


@dataclass(frozen=True)
class FlaggedSource:
    source: SearchResult
    reasons: tuple[str, ...]


def partition_adversarial_sources(
    sources: list[SearchResult],
) -> tuple[list[SearchResult], list[FlaggedSource]]:
    usable: list[SearchResult] = []
    flagged: list[FlaggedSource] = []
    for source in sources:
        reasons = detect_prompt_injection(source.text)
        if reasons:
            flagged.append(FlaggedSource(source=source, reasons=tuple(reasons)))
        else:
            usable.append(source)
    return usable, flagged


def detect_prompt_injection(text: str) -> list[str]:
    normalized = _normalize(text)
    return [
        reason
        for reason, pattern in _INJECTION_PATTERNS.items()
        if pattern.search(normalized)
    ]


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    without_accents = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return " ".join(without_accents.split())
