from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass

from preparador_audiencia.prescription_dates import parse_process_date
from preparador_audiencia.repositories import ChunkRecord

JUDGMENT_STRUCTURE_SCHEMA_VERSION = "1.0"
MAX_DECISIONS = 20
MAX_DECISION_PAGES = 30
MAX_ARTICLES = 40
MAX_PENALTIES = 20

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
_PENALTY_ANCHOR = re.compile(
    r"\b(?:pena\s*[- ]?\s*base|pena\s+(?:intermediaria|provisoria|definitiva)|"
    r"torno\s+definitiva|fixo\s+(?:a\s+)?pena|"
    r"condeno.{0,100}?(?:a|na)\s+pena)\b",
    re.IGNORECASE | re.DOTALL,
)
_NUMBER_WORDS = {
    "zero": 0,
    "um": 1,
    "uma": 1,
    "dois": 2,
    "duas": 2,
    "tres": 3,
    "quatro": 4,
    "cinco": 5,
    "seis": 6,
    "sete": 7,
    "oito": 8,
    "nove": 9,
    "dez": 10,
    "onze": 11,
    "doze": 12,
    "treze": 13,
    "quatorze": 14,
    "catorze": 14,
    "quinze": 15,
    "dezesseis": 16,
    "dezessete": 17,
    "dezoito": 18,
    "dezenove": 19,
    "vinte": 20,
    "trinta": 30,
    "quarenta": 40,
    "cinquenta": 50,
    "sessenta": 60,
    "setenta": 70,
    "oitenta": 80,
    "noventa": 90,
    "cem": 100,
}
_NUMBER_EXPRESSION = (
    r"(?:\d{1,3}(?:\s*\([^)]{1,40}\))?|"
    r"(?:zero|um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|dez|"
    r"onze|doze|treze|quatorze|catorze|quinze|dezesseis|dezessete|dezoito|"
    r"dezenove|vinte|trinta|quarenta|cinquenta|sessenta|setenta|oitenta|"
    r"noventa|cem)(?:\s+e\s+(?:um|uma|dois|duas|tres|quatro|cinco|seis|"
    r"sete|oito|nove))?)"
)


@dataclass(frozen=True)
class JudgmentStructureBuildResult:
    status: str
    decisions: list[dict[str, object]]
    final_judgments: list[dict[str, object]]
    warnings: list[str]


@dataclass(frozen=True)
class _Page:
    number: int
    text: str
    source_confidence: str


def build_judgment_structure(
    chunks: list[ChunkRecord],
) -> JudgmentStructureBuildResult:
    pages = _reconstruct_pages(chunks)
    starts = [
        (number, decision_type)
        for number, page in sorted(pages.items())
        if (decision_type := _decision_heading(page.text)) is not None
    ][:MAX_DECISIONS]
    decisions = []
    for index, (start_page, decision_type) in enumerate(starts):
        next_start = starts[index + 1][0] if index + 1 < len(starts) else None
        selected = _collect_decision_pages(start_page, next_start, pages)
        if selected:
            decisions.append(_build_decision(decision_type, selected))

    final_judgments = _extract_final_judgments(pages)
    warnings: list[str] = []
    if len(starts) == MAX_DECISIONS:
        warnings.append(
            f"O limite de {MAX_DECISIONS} decisoes foi atingido; revise o processo."
        )
    if not decisions:
        warnings.append("Nenhuma sentenca ou acordao com cabecalho reconhecivel foi localizado.")
    if not final_judgments:
        warnings.append("Nenhuma certidao de transito em julgado foi localizada.")
    warnings.append(
        "Os campos foram extraidos literalmente e precisam ser conferidos antes de "
        "alimentar calculos baseados na pena aplicada ou no transito em julgado."
    )
    if not decisions:
        status = "nao_localizada"
    elif any(bool(item["revisao_necessaria"]) for item in decisions):
        status = "revisao_necessaria"
    else:
        status = "concluido"
    return JudgmentStructureBuildResult(status, decisions, final_judgments, warnings)


def _reconstruct_pages(chunks: list[ChunkRecord]) -> dict[int, _Page]:
    grouped: dict[int, list[ChunkRecord]] = defaultdict(list)
    for chunk in chunks:
        if chunk.text.strip():
            grouped[chunk.page_number].append(chunk)
    pages = {}
    for number, page_chunks in grouped.items():
        ordered = sorted(page_chunks, key=lambda item: item.chunk_index)
        text = _merge_chunk_texts([item.text for item in ordered])
        confidence = _lowest_confidence(
            [item.source_confidence for item in ordered]
        )
        pages[number] = _Page(number, text, confidence)
    return pages


def _decision_heading(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()][:60]
    for line in lines:
        compact = _compact(line)
        if compact in {"sentenca", "sentencacriminal", "sentencapenal"} or (
            compact.startswith("sentenca") and len(compact) <= 50
        ):
            return "sentenca"
        if compact in {"acordao", "acordaocriminal"} or (
            compact.startswith("acordao") and len(compact) <= 50
        ):
            return "acordao"
    return None


def _collect_decision_pages(
    start_page: int,
    next_start: int | None,
    pages: dict[int, _Page],
) -> list[_Page]:
    selected = []
    for offset in range(MAX_DECISION_PAGES):
        page_number = start_page + offset
        if next_start is not None and page_number >= next_start:
            break
        page = pages.get(page_number)
        if page is None:
            break
        if offset and _certificate_heading(page.text):
            break
        selected.append(page)
    return selected


def _certificate_heading(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()][:30]
    return any(
        _compact(line).startswith("certidaodetransitoemjulgado") for line in lines
    )


def _build_decision(decision_type: str, pages: list[_Page]) -> dict[str, object]:
    full_text, page_ranges = _text_with_page_ranges(pages)
    disposition = _extract_disposition(full_text, page_ranges)
    decision_scope = str(disposition["texto"]) if disposition is not None else full_text
    scope_start = full_text.find(decision_scope) if disposition is not None else 0
    result = _decision_result(decision_scope)
    penalties = _extract_penalties(pages)
    fine = _extract_fine(pages)
    regime = _extract_regime(pages)
    substitution = _extract_binary_decision(
        pages,
        positive=("substituo a pena privativa", "substituida por penas restritivas"),
        negative=("deixo de substituir", "nao substituo a pena"),
    )
    sursis = _extract_binary_decision(
        pages,
        positive=("concedo a suspensao condicional", "concedo o sursis"),
        negative=("deixo de conceder o sursis", "nao concedo o sursis"),
    )
    applied_articles = _extract_articles(decision_scope, scope_start, page_ranges)
    warnings = []
    if disposition is None:
        warnings.append("O inicio do dispositivo nao foi localizado com seguranca.")
    if result in {"condenatoria", "mista"} and not any(
        item["fase"] == "definitiva" for item in penalties
    ):
        warnings.append("A pena definitiva nao foi identificada com seguranca.")
    if result == "nao_identificado":
        warnings.append("O resultado condenatorio ou absolutorio precisa ser conferido.")
    if any(page.source_confidence not in {"alta", "media"} for page in pages):
        warnings.append("Ha paginas com confianca de extracao baixa ou desconhecida.")
    review_required = bool(warnings)
    return {
        "id_decisao": _decision_id(decision_type, pages[0].number, decision_scope),
        "tipo_documento": decision_type,
        "resultado": result,
        "pagina_inicial": pages[0].number,
        "pagina_final": pages[-1].number,
        "dispositivo": disposition,
        "artigos_aplicados": applied_articles,
        "penas_aplicadas": penalties,
        "multa": fine,
        "regime_inicial": regime,
        "substituicao_pena": substitution,
        "sursis": sursis,
        "confianca_fonte": _lowest_confidence(
            [page.source_confidence for page in pages]
        ),
        "revisao_necessaria": review_required,
        "avisos": warnings,
    }


def _extract_disposition(
    text: str,
    page_ranges: list[tuple[int, int, int]],
) -> dict[str, object] | None:
    folded = _fold(text)
    positions = [
        folded.rfind(marker)
        for marker in (
            "ante o exposto",
            "diante do exposto",
            "isto posto",
            "por tais razoes",
        )
    ]
    positions = [position for position in positions if position >= 0]
    if not positions:
        positions = [folded.rfind("julgo ")]
    start = max(positions) if positions and max(positions) >= 0 else -1
    if start < 0:
        return None
    end = min(len(text), start + 7000)
    pages = [
        page for page, range_start, range_end in page_ranges
        if range_end > start and range_start < end
    ]
    return {"texto": text[start:end].strip(), "paginas": pages}


def _decision_result(text: str) -> str:
    folded = _fold(text)
    has_conviction = bool(re.search(r"\b(?:condeno|condenar)\b", folded))
    has_acquittal = bool(re.search(r"\b(?:absolvo|absolver)\b", folded))
    if has_conviction and has_acquittal:
        return "mista"
    if has_conviction:
        return "condenatoria"
    if has_acquittal:
        return "absolutoria"
    return "nao_identificado"


def _extract_penalties(pages: list[_Page]) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    seen: set[tuple[object, ...]] = set()
    for page in pages:
        folded = _fold(page.text)
        anchors = list(_PENALTY_ANCHOR.finditer(folded))
        for index, anchor in enumerate(anchors):
            next_start = anchors[index + 1].start() if index + 1 < len(anchors) else None
            end = min(
                len(page.text),
                anchor.start() + 420,
                next_start if next_start is not None else len(page.text),
            )
            original_window = page.text[anchor.start():end]
            folded_window = folded[anchor.start():end]
            species = _penalty_species(folded_window)
            years = _duration_component(folded_window, "ano")
            months = _duration_component(folded_window, "mes")
            days = _duration_component(folded_window, "dia")
            if species is None or not any(value is not None for value in (years, months, days)):
                continue
            phase = _penalty_phase(anchor.group(0))
            key = (phase, species, years, months, days, page.number)
            if key in seen:
                continue
            seen.add(key)
            found.append(
                {
                    "fase": phase,
                    "especie": species,
                    "anos": years or 0,
                    "meses": months or 0,
                    "dias": days or 0,
                    "pagina": page.number,
                    "trecho": " ".join(original_window.split()),
                }
            )
            if len(found) >= MAX_PENALTIES:
                return found
    return found


def _penalty_phase(anchor: str) -> str:
    folded = _fold(anchor)
    if "base" in folded:
        return "base"
    if "intermediaria" in folded or "provisoria" in folded:
        return "intermediaria"
    if "definitiva" in folded:
        return "definitiva"
    return "nao_identificada"


def _penalty_species(text: str) -> str | None:
    if "reclusao" in text:
        return "reclusao"
    if "detencao" in text:
        return "detencao"
    if "prisao simples" in text:
        return "prisao_simples"
    return None


def _duration_component(text: str, unit: str) -> int | None:
    suffix = {"ano": r"anos?", "mes": r"mes(?:es)?", "dia": r"dias?"}[unit]
    fine_guard = r"(?!\s*[- ]?\s*multa)" if unit == "dia" else ""
    match = re.search(
        rf"(?P<number>{_NUMBER_EXPRESSION})\s+{suffix}\b{fine_guard}",
        text,
    )
    return _parse_number(match.group("number")) if match else None


def _parse_number(value: str) -> int | None:
    digit = re.match(r"\d{1,3}", value.strip())
    if digit:
        return int(digit.group(0))
    parts = [part.strip() for part in value.split(" e ") if part.strip()]
    if not parts or any(part not in _NUMBER_WORDS for part in parts):
        return None
    return sum(_NUMBER_WORDS[part] for part in parts)


def _extract_fine(pages: list[_Page]) -> dict[str, object] | None:
    pattern = re.compile(rf"(?P<number>{_NUMBER_EXPRESSION})\s+dias?\s*[- ]?\s*multa")
    for page in pages:
        folded = _fold(page.text)
        matches = list(pattern.finditer(folded))
        if not matches:
            continue
        match = matches[-1]
        days = _parse_number(match.group("number"))
        if days is None:
            continue
        start = max(0, match.start() - 120)
        end = min(len(page.text), match.end() + 180)
        return {
            "dias_multa": days,
            "pagina": page.number,
            "trecho": " ".join(page.text[start:end].split()),
        }
    return None


def _extract_regime(pages: list[_Page]) -> dict[str, object] | None:
    pattern = re.compile(
        r"regime(?:\s+inicial)?(?:\s+de\s+cumprimento)?[^.]{0,100}?"
        r"\b(fechado|semiaberto|aberto)\b",
        re.IGNORECASE,
    )
    for page in reversed(pages):
        folded = _fold(page.text)
        match = pattern.search(folded)
        if match:
            start = max(0, match.start() - 100)
            end = min(len(page.text), match.end() + 120)
            return {
                "valor": match.group(1).lower(),
                "pagina": page.number,
                "trecho": " ".join(page.text[start:end].split()),
            }
    return None


def _extract_binary_decision(
    pages: list[_Page],
    *,
    positive: tuple[str, ...],
    negative: tuple[str, ...],
) -> dict[str, object]:
    for page in reversed(pages):
        folded = _fold(page.text)
        matches = [
            (folded.rfind(marker), "deferida") for marker in positive
        ] + [
            (folded.rfind(marker), "indeferida") for marker in negative
        ]
        position, result = max(matches, key=lambda item: item[0])
        if position >= 0:
            end = min(len(page.text), position + 500)
            return {
                "resultado": result,
                "pagina": page.number,
                "trecho": " ".join(page.text[position:end].split()),
            }
    return {"resultado": "nao_localizada", "pagina": None, "trecho": None}


def _extract_articles(
    decision_scope: str,
    scope_start: int,
    page_ranges: list[tuple[int, int, int]],
) -> list[dict[str, object]]:
    found = []
    seen = set()
    for match in _ARTICLE_PATTERN.finditer(decision_scope):
        article = " ".join(match.group(0).split())
        key = _fold(article)
        if key in seen:
            continue
        seen.add(key)
        start = max(0, match.start() - 100)
        end = min(len(decision_scope), match.end() + 140)
        absolute_position = scope_start + match.start()
        page = next(
            (
                page_number
                for page_number, range_start, range_end in page_ranges
                if range_start <= absolute_position < range_end
            ),
            page_ranges[-1][0],
        )
        found.append(
            {
                "artigo": article,
                "pagina": page,
                "trecho": " ".join(decision_scope[start:end].split()),
            }
        )
        if len(found) >= MAX_ARTICLES:
            break
    return found


def _extract_final_judgments(pages: dict[int, _Page]) -> list[dict[str, object]]:
    found: dict[tuple[str, str], dict[str, object]] = {}
    marker_pattern = re.compile(r"transit(?:o|ou)\s+em\s+julgado", re.IGNORECASE)
    for page in pages.values():
        folded = _fold(page.text)
        for marker in marker_pattern.finditer(folded):
            start = max(0, marker.start() - 260)
            end = min(len(page.text), marker.end() + 500)
            window = page.text[start:end]
            date_matches = list(_DATE_PATTERN.finditer(window))
            if not date_matches:
                continue
            selected = min(
                date_matches,
                key=lambda item: abs((start + item.start()) - marker.start()),
            )
            parsed = parse_process_date(selected.group(0))
            if parsed is None:
                continue
            folded_window = _fold(window)
            scope = _final_judgment_scope(folded_window)
            key = (scope, parsed.isoformat())
            found.setdefault(
                key,
                {
                    "id_transito": _final_judgment_id(scope, parsed.isoformat(), page.number),
                    "escopo": scope,
                    "data": parsed.isoformat(),
                    "pagina": page.number,
                    "trecho": " ".join(window.split()),
                    "confianca_fonte": page.source_confidence,
                    "revisao_necessaria": True,
                },
            )
    return sorted(found.values(), key=lambda item: (str(item["data"]), str(item["escopo"])))


def _final_judgment_scope(text: str) -> str:
    if "ambas as partes" in text or "acusacao e defesa" in text:
        return "ambas_partes"
    if "acusacao" in text or "ministerio publico" in text:
        return "acusacao"
    if "defesa" in text or "reu" in text or "acusado" in text:
        return "defesa"
    return "indefinido"


def _text_with_page_ranges(pages: list[_Page]) -> tuple[str, list[tuple[int, int, int]]]:
    text = ""
    ranges = []
    for page in pages:
        if text:
            text += "\n\n"
        start = len(text)
        text += page.text
        ranges.append((page.number, start, len(text)))
    return text, ranges


def _merge_chunk_texts(texts: list[str]) -> str:
    merged = ""
    for raw in texts:
        text = raw.strip()
        if not text:
            continue
        if not merged:
            merged = text
        elif text not in merged[-(len(text) + 600):]:
            merged += f"\n{text}"
    return merged


def _decision_id(decision_type: str, page: int, text: str) -> str:
    digest = hashlib.sha256(
        f"{decision_type}|{page}|{text[:1000]}".encode()
    ).hexdigest()[:14]
    return f"dec-{digest}"


def _final_judgment_id(scope: str, value: str, page: int) -> str:
    digest = hashlib.sha256(f"{scope}|{value}|{page}".encode()).hexdigest()[:14]
    return f"trans-{digest}"


def _lowest_confidence(values: list[str]) -> str:
    rank = {"desconhecida": 0, "baixa": 1, "media": 2, "alta": 3}
    normalized = [item if item in rank else "desconhecida" for item in values]
    return min(normalized, key=lambda item: rank[item]) if normalized else "desconhecida"


def _compact(value: str) -> str:
    return "".join(char for char in _fold(value) if char.isalnum())


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))
