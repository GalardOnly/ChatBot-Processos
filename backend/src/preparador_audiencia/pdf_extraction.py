from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import fitz

from preparador_audiencia.ocr import OcrEngine, OcrResult, get_configured_ocr_engine

DEFAULT_SAMPLE_CHARS = 500
LOW_TEXT_THRESHOLD = 80
IMAGE_WITH_SPARSE_TEXT_THRESHOLD = 500
DEFAULT_OCR_BATCH_SIZE = 4
OCR_MIN_REVIEW_CHARS = 160
OCR_MIN_REVIEW_WORDS = 20
GLUED_TEXT_MIN_CHARS = 1_000
GLUED_TEXT_MAX_SPACE_RATIO = 0.07
GLUED_TEXT_LONG_TOKEN_CHARS = 40
GLUED_TEXT_MIN_LONG_TOKENS = 3

ExtractionProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True)
class PageExtraction:
    page_number: int
    char_count: int
    word_count: int
    native_char_count: int
    image_count: int
    ocr_applied: bool
    ocr_char_count: int
    extraction_method: str
    full_text: str
    text_sample: str
    is_probably_empty: bool
    quality_notes: list[str]
    source_confidence: str = "alta"
    ocr_engine: str | None = None
    ocr_engine_version: str | None = None
    ocr_device: str | None = None
    ocr_cache_hit: bool = False
    ocr_fallback_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PdfExtractionReport:
    file_name: str
    page_count: int
    total_char_count: int
    empty_page_count: int
    low_text_page_count: int
    pages: list[PageExtraction]

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_name": self.file_name,
            "page_count": self.page_count,
            "total_char_count": self.total_char_count,
            "empty_page_count": self.empty_page_count,
            "low_text_page_count": self.low_text_page_count,
            "pages": [page.to_dict() for page in self.pages],
        }


@dataclass(frozen=True)
class _PageDraft:
    page: fitz.Page
    page_number: int
    native_text: str
    image_count: int
    should_run_ocr: bool
    native_layout_issue: bool


def extract_pdf_report(
    pdf_path: str | Path,
    sample_chars: int = DEFAULT_SAMPLE_CHARS,
    ocr_enabled: bool = True,
    ocr_zoom: float = 1.5,
    ocr_workers: int = 2,
    ocr_engine: OcrEngine | None = None,
    max_pages: int | None = None,
    progress_callback: ExtractionProgressCallback | None = None,
) -> PdfExtractionReport:
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF nao encontrado: {path}")
    if not path.is_file():
        raise ValueError(f"Caminho nao e arquivo: {path}")

    pages: list[PageExtraction] = []
    resolved_ocr_engine: OcrEngine | None = ocr_engine
    with fitz.open(path) as document:
        total_pages = document.page_count
        if max_pages is not None:
            total_pages = min(total_pages, max_pages)
        batch_size = max(DEFAULT_OCR_BATCH_SIZE, max(1, ocr_workers) * 2)

        for batch_start in range(0, total_pages, batch_size):
            batch_end = min(batch_start + batch_size, total_pages)
            drafts = [
                _create_page_draft(document[page_index], page_index, ocr_enabled)
                for page_index in range(batch_start, batch_end)
            ]
            has_ocr = any(draft.should_run_ocr for draft in drafts)
            if has_ocr and resolved_ocr_engine is None:
                resolved_ocr_engine = get_configured_ocr_engine()

            ocr_results = _extract_ocr_batch(
                drafts,
                resolved_ocr_engine,
                ocr_zoom=ocr_zoom,
            )
            for draft, ocr_result in zip(drafts, ocr_results, strict=True):
                pages.append(
                    _finish_page_extraction(
                        draft,
                        ocr_result=replace(
                            ocr_result,
                            text=normalize_text(ocr_result.text),
                        ),
                        sample_chars=sample_chars,
                    )
                )
                if progress_callback is not None:
                    progress_callback(len(pages), total_pages)

    return PdfExtractionReport(
        file_name=path.name,
        page_count=len(pages),
        total_char_count=sum(page.char_count for page in pages),
        empty_page_count=sum(1 for page in pages if page.is_probably_empty),
        low_text_page_count=sum(
            1 for page in pages if "baixo_texto_extraido" in page.quality_notes
        ),
        pages=pages,
    )


def _create_page_draft(
    page: fitz.Page,
    page_index: int,
    ocr_enabled: bool,
) -> _PageDraft:
    native_text = normalize_text(page.get_text("text"))
    image_count = len(page.get_images(full=True))
    native_layout_issue = has_glued_text(native_text)
    return _PageDraft(
        page=page,
        page_number=page_index + 1,
        native_text=native_text,
        image_count=image_count,
        should_run_ocr=ocr_enabled
        and (_should_run_ocr(native_text, image_count) or native_layout_issue),
        native_layout_issue=native_layout_issue,
    )


def _extract_ocr_batch(
    drafts: list[_PageDraft],
    ocr_engine: OcrEngine | None,
    *,
    ocr_zoom: float,
) -> list[OcrResult]:
    results = [_empty_ocr_result() for _draft in drafts]
    candidates = [
        (index, draft)
        for index, draft in enumerate(drafts)
        if draft.should_run_ocr
    ]
    if not candidates:
        return results

    if ocr_engine is not None:
        extract_pages = getattr(ocr_engine, "extract_pages", None)
        if callable(extract_pages):
            batch_results = extract_pages(
                [draft.page for _index, draft in candidates],
                ocr_zoom,
            )
            if len(batch_results) != len(candidates):
                raise RuntimeError("Motor OCR devolveu quantidade inesperada de paginas.")
            for (index, _draft), result in zip(candidates, batch_results, strict=True):
                results[index] = result
            return results
        for index, draft in candidates:
            text = ocr_engine.extract_page_text(draft.page, zoom=ocr_zoom)
            results[index] = OcrResult(
                text=text,
                engine=str(
                    getattr(ocr_engine, "name", ocr_engine.__class__.__name__.lower())
                ),
                engine_version=_optional_text(
                    getattr(ocr_engine, "engine_version", None)
                ),
                device=_optional_text(getattr(ocr_engine, "device", None)),
            )
    return results


def _finish_page_extraction(
    draft: _PageDraft,
    *,
    ocr_result: OcrResult,
    sample_chars: int,
) -> PageExtraction:
    ocr_text = ocr_result.text
    ocr_replaced_native = _should_prefer_ocr_text(draft, ocr_text)
    text = (
        ocr_text
        if ocr_replaced_native
        else _merge_native_and_ocr_text(draft.native_text, ocr_text)
    )
    source_confidence = _source_confidence(
        draft.native_text,
        ocr_applied=draft.should_run_ocr,
        ocr_text=ocr_text,
        native_layout_issue=draft.native_layout_issue,
    )
    return PageExtraction(
        page_number=draft.page_number,
        char_count=len(text),
        word_count=len(text.split()),
        native_char_count=len(draft.native_text),
        image_count=draft.image_count,
        ocr_applied=draft.should_run_ocr,
        ocr_char_count=len(ocr_text),
        extraction_method=_extraction_method(
            draft.native_text,
            ocr_text,
            ocr_replaced_native=ocr_replaced_native,
        ),
        full_text=text,
        text_sample=text[:sample_chars],
        is_probably_empty=_is_probably_empty(text),
        quality_notes=_quality_notes(
            draft.native_text,
            image_count=draft.image_count,
            ocr_applied=draft.should_run_ocr,
            ocr_text=ocr_text,
            source_confidence=source_confidence,
            native_layout_issue=draft.native_layout_issue,
            ocr_replaced_native=ocr_replaced_native,
            ocr_result=ocr_result,
        ),
        source_confidence=source_confidence,
        ocr_engine=ocr_result.engine,
        ocr_engine_version=ocr_result.engine_version,
        ocr_device=ocr_result.device,
        ocr_cache_hit=ocr_result.cache_hit,
        ocr_fallback_used=ocr_result.fallback_used,
    )


def normalize_text(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.replace("\r", "\n").split("\n")]
    compact_lines = [line for line in lines if line]
    return "\n".join(compact_lines).strip()


def _is_probably_empty(text: str) -> bool:
    return len(text.strip()) == 0


def _quality_notes(
    native_text: str,
    image_count: int = 0,
    ocr_applied: bool = False,
    ocr_text: str = "",
    source_confidence: str = "alta",
    native_layout_issue: bool = False,
    ocr_replaced_native: bool = False,
    ocr_result: OcrResult | None = None,
) -> list[str]:
    notes: list[str] = []
    if native_layout_issue:
        notes.append("texto_nativo_com_palavras_coladas")
    if ocr_applied:
        notes.append("ocr_aplicado")
        if ocr_text.strip():
            notes.append("ocr_com_texto")
            if has_glued_text(ocr_text):
                notes.append("ocr_com_palavras_coladas")
        else:
            notes.append("ocr_sem_texto")
        if ocr_replaced_native:
            notes.append("ocr_substituiu_texto_nativo_inadequado")
        if ocr_result is not None and ocr_result.engine:
            notes.append(f"ocr_motor_{ocr_result.engine}")
        if ocr_result is not None and ocr_result.cache_hit:
            notes.append("ocr_resultado_reutilizado_do_cache")
        if ocr_result is not None and ocr_result.fallback_used:
            notes.append("ocr_fallback_rapidocr")
        notes.append(f"confianca_{source_confidence}")

    text = native_text
    if not text.strip():
        notes.append("sem_texto_nativo")
        if image_count:
            notes.append("possivel_pagina_escaneada_ou_imagem")
        return notes
    if image_count and len(text) < IMAGE_WITH_SPARSE_TEXT_THRESHOLD:
        notes.extend(["imagem_com_texto_curto", "provavel_necessidade_de_ocr"])
        return notes
    if len(text) < LOW_TEXT_THRESHOLD:
        notes.append("baixo_texto_extraido")
        return notes
    notes.append("texto_nativo_extraido")
    return notes


def _should_run_ocr(native_text: str, image_count: int) -> bool:
    if not image_count:
        return False
    return not native_text.strip() or len(native_text) < IMAGE_WITH_SPARSE_TEXT_THRESHOLD


def has_glued_text(text: str) -> bool:
    if len(text) < GLUED_TEXT_MIN_CHARS:
        return False
    space_ratio = text.count(" ") / len(text)
    if space_ratio > GLUED_TEXT_MAX_SPACE_RATIO:
        return False
    long_tokens = sum(
        len(token) >= GLUED_TEXT_LONG_TOKEN_CHARS
        for token in text.replace("\n", " ").split()
    )
    return long_tokens >= GLUED_TEXT_MIN_LONG_TOKENS


def _should_prefer_ocr_text(draft: _PageDraft, ocr_text: str) -> bool:
    if not _is_substantial_ocr(ocr_text):
        return False
    native_is_sparse_image_layer = (
        bool(draft.image_count)
        and len(draft.native_text) < IMAGE_WITH_SPARSE_TEXT_THRESHOLD
    )
    return draft.native_layout_issue or native_is_sparse_image_layer


def _merge_native_and_ocr_text(native_text: str, ocr_text: str) -> str:
    parts = [part for part in (native_text, ocr_text) if part.strip()]
    return "\n\n".join(parts)


def _extraction_method(
    native_text: str,
    ocr_text: str,
    *,
    ocr_replaced_native: bool = False,
) -> str:
    if ocr_replaced_native:
        return "ocr_recovery"
    has_native = bool(native_text.strip())
    has_ocr = bool(ocr_text.strip())
    if has_native and has_ocr:
        return "native_plus_ocr"
    if has_ocr:
        return "ocr"
    if has_native:
        return "native"
    return "empty"


def _source_confidence(
    native_text: str,
    *,
    ocr_applied: bool,
    ocr_text: str,
    native_layout_issue: bool = False,
) -> str:
    if not ocr_applied:
        return "alta" if native_text.strip() else "baixa"
    if native_layout_issue:
        return (
            "media"
            if _is_substantial_ocr(ocr_text) and not has_glued_text(ocr_text)
            else "baixa"
        )
    if len(native_text) >= IMAGE_WITH_SPARSE_TEXT_THRESHOLD:
        return "alta"
    if _is_substantial_ocr(ocr_text) and not has_glued_text(ocr_text):
        return "media"
    return "baixa"


def _is_substantial_ocr(ocr_text: str) -> bool:
    return (
        len(ocr_text) >= OCR_MIN_REVIEW_CHARS
        and len(ocr_text.split()) >= OCR_MIN_REVIEW_WORDS
    )


def _empty_ocr_result() -> OcrResult:
    return OcrResult(text="", engine=None, engine_version=None, device=None)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
