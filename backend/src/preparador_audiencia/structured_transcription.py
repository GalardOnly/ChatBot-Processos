from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass

from preparador_audiencia.pdf_extraction import has_glued_text
from preparador_audiencia.repositories import ChunkRecord
from preparador_audiencia.testimony_identification import identify_testimony_person

MAX_TESTIMONIES = 100
MAX_PAGES_WITHOUT_HINT = 4
MAX_PAGES_FROM_HINT = 12
MAX_HEADING_POSITION = 5000
MAX_OVERLAP_CHECK = 600

_CONFIDENCE_RANK = {
    "desconhecida": 0,
    "baixa": 1,
    "media": 2,
    "alta": 3,
}
_CLOSING_MARKERS = (
    "nadamaisdisse",
    "nadamaisdeclarou",
    "nadalhefoiperguntado",
    "fosseencerradoestetermo",
    "encerrouseopresente",
    "encerradoopresente",
)
_OTHER_DOCUMENT_MARKERS = (
    "certidao",
    "relatoriofinal",
    "laudopericial",
    "laudodeexame",
    "mandadode",
    "decisao",
    "sentenca",
    "denuncia",
)


@dataclass(frozen=True)
class TranscriptionBuildResult:
    status: str
    testimonies: list[dict[str, object]]
    warnings: list[str]


@dataclass(frozen=True)
class _PageText:
    number: int
    text: str
    source_confidence: str
    has_glued_words: bool
    ocr_engine: str | None
    ocr_engine_version: str | None
    ocr_device: str | None
    ocr_cache_hit: bool
    ocr_fallback_used: bool


@dataclass(frozen=True)
class _DocumentStart:
    document_type: str
    title: str
    role: str


def build_structured_transcription(
    chunks: list[ChunkRecord],
) -> TranscriptionBuildResult:
    pages = _reconstruct_pages(chunks)
    starts = [
        (page_number, detected)
        for page_number, page in sorted(pages.items())
        if (detected := _detect_document_start(page.text)) is not None
    ]
    warnings: list[str] = []
    if len(starts) > MAX_TESTIMONIES:
        warnings.append(
            f"Foram localizados mais de {MAX_TESTIMONIES} termos; apenas os primeiros "
            f"{MAX_TESTIMONIES} foram estruturados."
        )
        starts = starts[:MAX_TESTIMONIES]

    testimonies: list[dict[str, object]] = []
    start_pages = {page_number for page_number, _ in starts}
    for index, (page_number, detected) in enumerate(starts):
        next_start = starts[index + 1][0] if index + 1 < len(starts) else None
        selected, coverage, item_warnings = _collect_document_pages(
            page_number,
            pages,
            start_pages,
            next_start,
        )
        if not selected:
            continue
        testimonies.append(
            _build_testimony(
                order=len(testimonies) + 1,
                detected=detected,
                pages=selected,
                coverage=coverage,
                initial_warnings=item_warnings,
            )
        )

    if not testimonies:
        warnings.append(
            "Nenhum termo de declaracao, depoimento ou interrogatorio foi localizado "
            "pelos marcadores conhecidos."
        )
        return TranscriptionBuildResult(
            status="sem_depoimentos",
            testimonies=[],
            warnings=warnings,
        )

    if any(bool(item["revisao_necessaria"]) for item in testimonies):
        warnings.append(
            "Ha transcricoes que precisam de conferencia por cobertura, identidade ou "
            "qualidade da extracao."
        )
        status = "revisao_necessaria"
    else:
        status = "concluido"
    warnings.append(
        "Os textos reproduzem a extracao armazenada e nao foram resumidos nem "
        "reescritos por modelo generativo."
    )
    return TranscriptionBuildResult(
        status=status,
        testimonies=testimonies,
        warnings=warnings,
    )


def _reconstruct_pages(chunks: list[ChunkRecord]) -> dict[int, _PageText]:
    grouped: dict[int, list[ChunkRecord]] = defaultdict(list)
    for chunk in chunks:
        if chunk.text.strip():
            grouped[chunk.page_number].append(chunk)

    pages: dict[int, _PageText] = {}
    for page_number, page_chunks in grouped.items():
        ordered = sorted(page_chunks, key=lambda chunk: chunk.chunk_index)
        text = _merge_chunk_texts([chunk.text for chunk in ordered])
        confidence = _lowest_confidence(
            [chunk.source_confidence for chunk in ordered]
        )
        pages[page_number] = _PageText(
            number=page_number,
            text=text,
            source_confidence=confidence,
            has_glued_words=_has_glued_layout(text),
            ocr_engine=_first_text([chunk.ocr_engine for chunk in ordered]),
            ocr_engine_version=_first_text(
                [chunk.ocr_engine_version for chunk in ordered]
            ),
            ocr_device=_first_text([chunk.ocr_device for chunk in ordered]),
            ocr_cache_hit=any(chunk.ocr_cache_hit for chunk in ordered),
            ocr_fallback_used=any(chunk.ocr_fallback_used for chunk in ordered),
        )
    return pages


def _merge_chunk_texts(texts: list[str]) -> str:
    merged = ""
    for raw_text in texts:
        text = raw_text.strip()
        if not text:
            continue
        if not merged:
            merged = text
            continue
        if text in merged[-(len(text) + MAX_OVERLAP_CHECK) :]:
            continue
        overlap = _largest_overlap(merged, text)
        if overlap:
            merged += text[overlap:]
        else:
            merged += f"\n{text}"
    return merged.strip()


def _largest_overlap(left: str, right: str) -> int:
    limit = min(len(left), len(right), MAX_OVERLAP_CHECK)
    for size in range(limit, 0, -1):
        if left.endswith(right[:size]):
            return size
    return 0


def _detect_document_start(text: str) -> _DocumentStart | None:
    compact = _compact(text)
    if not _has_form_context(compact):
        return None
    interrogation_position = _first_marker_position(
        compact,
        ("termodeinterrogatorio", "autodequalificacaoeinterrogatorio"),
    )
    if _is_heading_position(interrogation_position) and _has_heading_marker(
        text,
        ("termodeinterrogatorio", "autodequalificacaoeinterrogatorio"),
    ):
        return _DocumentStart("interrogatorio_reu", "Termo de interrogatorio", "reu")

    testimony_position = _first_marker_position(
        compact,
        ("termodedepoimento", "termodeoitiva"),
    )
    if _is_heading_position(testimony_position) and _has_heading_marker(
        text,
        ("termodedepoimento", "termodeoitiva"),
    ):
        context = compact[testimony_position : testimony_position + 700]
        if "condutor" in context:
            return _DocumentStart(
                "depoimento_condutor",
                "Termo de depoimento do condutor",
                "condutor",
            )
        if any(
            marker in context
            for marker in ("prestaavitima", "depoimentodavitima", "oitivadavitima")
        ):
            return _DocumentStart(
                "depoimento_vitima",
                "Termo de depoimento da vitima",
                "vitima",
            )
        if "informante" in context:
            return _DocumentStart(
                "depoimento_informante",
                "Termo de depoimento de informante",
                "informante",
            )
        return _DocumentStart(
            "depoimento_testemunha",
            "Termo de depoimento de testemunha",
            "testemunha",
        )

    declarations_position = compact.find("termodedeclaracoes")
    if _is_heading_position(declarations_position) and _has_heading_marker(
        text,
        ("termodedeclaracoes",),
    ):
        context = compact[declarations_position : declarations_position + 700]
        if any(
            marker in context
            for marker in ("prestaavitima", "declaracoesdavitima", "ofendido", "lesado")
        ):
            return _DocumentStart(
                "declaracoes_vitima",
                "Termo de declaracoes da vitima",
                "vitima",
            )
        return _DocumentStart(
            "declaracoes",
            "Termo de declaracoes",
            "declarante",
        )

    declaration_position = compact.find("termodedeclaracao")
    if _is_heading_position(declaration_position) and _has_heading_marker(
        text,
        ("termodedeclaracao",),
    ):
        return _DocumentStart(
            "declaracao",
            "Termo de declaracao",
            "declarante",
        )
    return None


def _collect_document_pages(
    start_page: int,
    pages: dict[int, _PageText],
    start_pages: set[int],
    next_start: int | None,
) -> tuple[list[_PageText], str, list[str]]:
    first_page = pages[start_page]
    total_hint = _page_total_hint(first_page.text)
    page_limit = total_hint or MAX_PAGES_WITHOUT_HINT
    selected: list[_PageText] = []
    warnings: list[str] = []
    closing_found = False
    interrupted = False

    for offset in range(page_limit):
        page_number = start_page + offset
        if next_start is not None and page_number >= next_start:
            interrupted = True
            break
        if offset and page_number in start_pages:
            interrupted = True
            break
        page = pages.get(page_number)
        if page is None:
            interrupted = True
            warnings.append(f"A pagina {page_number} nao possui texto armazenado.")
            break
        if offset and total_hint is None and _has_other_document_start(page.text):
            interrupted = True
            break
        selected.append(page)
        if _has_closing_marker(page.text):
            closing_found = True
            if total_hint is None:
                break

    expected_complete = (
        len(selected) == total_hint if total_hint is not None else closing_found
    )
    coverage = "integral" if expected_complete and closing_found and not interrupted else "parcial"
    if total_hint is not None and len(selected) != total_hint:
        warnings.append(
            f"O termo informa {total_hint} pagina(s), mas apenas {len(selected)} "
            "foram agrupadas."
        )
    if not closing_found:
        warnings.append("O encerramento formal do termo nao foi localizado.")
    if interrupted and not warnings:
        warnings.append("O agrupamento terminou no inicio de outro documento.")
    return selected, coverage, warnings


def _build_testimony(
    *,
    order: int,
    detected: _DocumentStart,
    pages: list[_PageText],
    coverage: str,
    initial_warnings: list[str],
) -> dict[str, object]:
    warnings = list(initial_warnings)
    consolidated = "\n\n".join(page.text for page in pages)
    identification = identify_testimony_person(
        [(page.number, page.text) for page in pages],
        detected.role,
    )
    person = identification.name
    if person is None:
        warnings.append("A pessoa ouvida nao foi identificada com seguranca.")
    elif identification.confidence == "media":
        warnings.append(
            "A pessoa ouvida foi identificada por qualificacao indireta e precisa "
            "ser conferida no cabecalho original."
        )

    glued_pages = [page.number for page in pages if page.has_glued_words]
    if glued_pages:
        warnings.append(
            "Ha palavras coladas na extracao das paginas "
            + ", ".join(str(page) for page in glued_pages)
            + "."
        )
    low_confidence_pages = [
        page.number
        for page in pages
        if page.source_confidence in {"baixa", "desconhecida"}
    ]
    if low_confidence_pages:
        warnings.append(
            "A fonte tem confianca baixa ou desconhecida nas paginas "
            + ", ".join(str(page) for page in low_confidence_pages)
            + "."
        )
    if coverage == "parcial" and not any("encerramento" in item for item in warnings):
        warnings.append("A cobertura integral do termo nao pode ser comprovada.")

    review_required = bool(
        coverage == "parcial"
        or identification.confidence != "alta"
        or glued_pages
        or low_confidence_pages
    )
    return {
        "id_depoimento": f"dep-p{pages[0].number:04d}-{detected.document_type}",
        "ordem": order,
        "tipo_documento": detected.document_type,
        "titulo": detected.title,
        "pessoa": person,
        "papel": detected.role,
        "identificacao": {
            "status": identification.status,
            "metodo": identification.method,
            "confianca": identification.confidence,
            "nome_normalizado": identification.normalized_name,
            "trecho_evidencia": identification.evidence,
            "pagina": identification.page_number,
        },
        "fase": _detect_phase(consolidated),
        "cobertura": coverage,
        "pagina_inicial": pages[0].number,
        "pagina_final": pages[-1].number,
        "paginas": [
            {
                "pagina": page.number,
                "texto": page.text,
                "confianca_fonte": page.source_confidence,
                "palavras_coladas": page.has_glued_words,
                "motor_ocr": page.ocr_engine,
                "versao_ocr": page.ocr_engine_version,
                "dispositivo_ocr": page.ocr_device,
                "cache_ocr": page.ocr_cache_hit,
                "fallback_ocr": page.ocr_fallback_used,
            }
            for page in pages
        ],
        "texto_consolidado": consolidated,
        "confianca_fonte": _lowest_confidence(
            [page.source_confidence for page in pages]
        ),
        "revisao_necessaria": review_required,
        "avisos": _unique(warnings),
    }


def _detect_phase(text: str) -> str:
    compact = _compact(text)
    if any(
        marker in compact
        for marker in (
            "inquerito",
            "delegacia",
            "policiacivil",
            "autodeprisaoemflagrante",
        )
    ):
        return "inquerito"
    if any(marker in compact for marker in ("audienciadeinstrucao", "emjuizo", "juizo")):
        return "juizo"
    return "outro"


def _page_total_hint(text: str) -> int | None:
    match = re.search(r"pag(?:ina)?1de(\d{1,2})", _compact(text))
    if match is None:
        return None
    total = int(match.group(1))
    return total if 1 <= total <= MAX_PAGES_FROM_HINT else None


def _has_closing_marker(text: str) -> bool:
    compact = _compact(text)
    return any(marker in compact for marker in _CLOSING_MARKERS)


def _has_form_context(compact: str) -> bool:
    return any(
        marker in compact
        for marker in (
            "inquerito",
            "policiacivil",
            "delegacia",
            "autodeprisaoemflagrante",
            "audienciadeinstrucao",
            "pag1de",
        )
    )


def _has_heading_marker(text: str, markers: tuple[str, ...]) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    candidates = [
        *lines,
        *(f"{left} {right}" for left, right in zip(lines, lines[1:], strict=False)),
    ]
    for line in candidates:
        compact_line = _compact(line)
        if not any(marker in compact_line for marker in markers):
            continue
        letters = [char for char in line if char.isalpha()]
        uppercase_ratio = (
            sum(char.isupper() for char in letters) / len(letters) if letters else 0.0
        )
        if uppercase_ratio >= 0.65:
            return True
        if any(compact_line.startswith(marker) for marker in markers) and len(line) <= 220:
            return True
    return False


def _has_other_document_start(text: str) -> bool:
    compact = _compact(text)
    positions = [compact.find(marker) for marker in _OTHER_DOCUMENT_MARKERS]
    return any(_is_heading_position(position) for position in positions)


def _has_glued_layout(text: str) -> bool:
    if has_glued_text(text):
        return True
    tokens = re.findall(r"\S+", text)
    long_tokens = [token for token in tokens if len(token) >= 35]
    return len(long_tokens) >= 3


def _lowest_confidence(values: list[str]) -> str:
    normalized = [value if value in _CONFIDENCE_RANK else "desconhecida" for value in values]
    if not normalized:
        return "desconhecida"
    return min(normalized, key=lambda value: _CONFIDENCE_RANK[value])


def _first_marker_position(text: str, markers: tuple[str, ...]) -> int:
    positions = [text.find(marker) for marker in markers]
    found = [position for position in positions if position >= 0]
    return min(found) if found else -1


def _is_heading_position(position: int) -> bool:
    return 0 <= position <= MAX_HEADING_POSITION


def _compact(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    return "".join(char.lower() for char in without_marks if char.isalnum())


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _first_text(values: list[str | None]) -> str | None:
    return next((value for value in values if value), None)
