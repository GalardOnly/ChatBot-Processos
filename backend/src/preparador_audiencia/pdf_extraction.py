from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import fitz

from preparador_audiencia.ocr import OcrEngine, RapidOcrEngine, RapidOcrPool

DEFAULT_SAMPLE_CHARS = 500
LOW_TEXT_THRESHOLD = 80
IMAGE_WITH_SPARSE_TEXT_THRESHOLD = 500
DEFAULT_OCR_BATCH_SIZE = 4

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
    ocr_pool: RapidOcrPool | None = None
    try:
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
                if has_ocr and resolved_ocr_engine is None and ocr_pool is None:
                    if ocr_workers > 1:
                        ocr_pool = RapidOcrPool(ocr_workers)
                    else:
                        resolved_ocr_engine = RapidOcrEngine()

                ocr_texts = _extract_ocr_batch(
                    drafts,
                    resolved_ocr_engine,
                    ocr_pool=ocr_pool,
                    ocr_zoom=ocr_zoom,
                )
                for draft, ocr_text in zip(drafts, ocr_texts, strict=True):
                    pages.append(
                        _finish_page_extraction(
                            draft,
                            ocr_text=normalize_text(ocr_text),
                            sample_chars=sample_chars,
                        )
                    )
                    if progress_callback is not None:
                        progress_callback(len(pages), total_pages)
    finally:
        if ocr_pool is not None:
            ocr_pool.close()

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
    return _PageDraft(
        page=page,
        page_number=page_index + 1,
        native_text=native_text,
        image_count=image_count,
        should_run_ocr=ocr_enabled and _should_run_ocr(native_text, image_count),
    )


def _extract_ocr_batch(
    drafts: list[_PageDraft],
    ocr_engine: OcrEngine | None,
    *,
    ocr_pool: RapidOcrPool | None,
    ocr_zoom: float,
) -> list[str]:
    texts = [""] * len(drafts)
    candidates = [
        (index, draft)
        for index, draft in enumerate(drafts)
        if draft.should_run_ocr
    ]
    if not candidates:
        return texts

    if ocr_pool is not None:
        images = [
            RapidOcrEngine.render_page_image(draft.page, ocr_zoom)
            for _index, draft in candidates
        ]
        results = ocr_pool.extract_images(images)
        for (index, _draft), result in zip(candidates, results, strict=True):
            texts[index] = result
        return texts

    if ocr_engine is not None:
        for index, draft in candidates:
            texts[index] = ocr_engine.extract_page_text(draft.page, zoom=ocr_zoom)
    return texts


def _finish_page_extraction(
    draft: _PageDraft,
    *,
    ocr_text: str,
    sample_chars: int,
) -> PageExtraction:
    text = _merge_native_and_ocr_text(draft.native_text, ocr_text)
    return PageExtraction(
        page_number=draft.page_number,
        char_count=len(text),
        word_count=len(text.split()),
        native_char_count=len(draft.native_text),
        image_count=draft.image_count,
        ocr_applied=draft.should_run_ocr,
        ocr_char_count=len(ocr_text),
        extraction_method=_extraction_method(draft.native_text, ocr_text),
        full_text=text,
        text_sample=text[:sample_chars],
        is_probably_empty=_is_probably_empty(text),
        quality_notes=_quality_notes(
            draft.native_text,
            image_count=draft.image_count,
            ocr_applied=draft.should_run_ocr,
            ocr_text=ocr_text,
        ),
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
) -> list[str]:
    notes: list[str] = []
    if ocr_applied:
        notes.append("ocr_aplicado")
        if ocr_text.strip():
            notes.append("ocr_com_texto")
        else:
            notes.append("ocr_sem_texto")

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


def _merge_native_and_ocr_text(native_text: str, ocr_text: str) -> str:
    parts = [part for part in (native_text, ocr_text) if part.strip()]
    return "\n\n".join(parts)


def _extraction_method(native_text: str, ocr_text: str) -> str:
    has_native = bool(native_text.strip())
    has_ocr = bool(ocr_text.strip())
    if has_native and has_ocr:
        return "native_plus_ocr"
    if has_ocr:
        return "ocr"
    if has_native:
        return "native"
    return "empty"
