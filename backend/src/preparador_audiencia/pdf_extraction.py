from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import fitz

from preparador_audiencia.ocr import OcrEngine, RapidOcrEngine

DEFAULT_SAMPLE_CHARS = 500
LOW_TEXT_THRESHOLD = 80
IMAGE_WITH_SPARSE_TEXT_THRESHOLD = 500


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


def extract_pdf_report(
    pdf_path: str | Path,
    sample_chars: int = DEFAULT_SAMPLE_CHARS,
    ocr_enabled: bool = True,
    ocr_zoom: float = 2.0,
    ocr_engine: OcrEngine | None = None,
    max_pages: int | None = None,
) -> PdfExtractionReport:
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF nao encontrado: {path}")
    if not path.is_file():
        raise ValueError(f"Caminho nao e arquivo: {path}")

    pages: list[PageExtraction] = []
    resolved_ocr_engine: OcrEngine | None = ocr_engine
    with fitz.open(path) as document:
        for page_index, page in enumerate(document):
            if max_pages is not None and page_index >= max_pages:
                break
            native_text = normalize_text(page.get_text("text"))
            image_count = len(page.get_images(full=True))
            should_run_ocr = ocr_enabled and _should_run_ocr(native_text, image_count)
            ocr_text = ""
            if should_run_ocr:
                if resolved_ocr_engine is None:
                    resolved_ocr_engine = RapidOcrEngine()
                ocr_text = normalize_text(
                    resolved_ocr_engine.extract_page_text(page, zoom=ocr_zoom)
                )
            text = _merge_native_and_ocr_text(native_text, ocr_text)
            pages.append(
                PageExtraction(
                    page_number=page_index + 1,
                    char_count=len(text),
                    word_count=len(text.split()),
                    native_char_count=len(native_text),
                    image_count=image_count,
                    ocr_applied=should_run_ocr,
                    ocr_char_count=len(ocr_text),
                    extraction_method=_extraction_method(native_text, ocr_text),
                    full_text=text,
                    text_sample=text[:sample_chars],
                    is_probably_empty=_is_probably_empty(text),
                    quality_notes=_quality_notes(
                        native_text,
                        image_count=image_count,
                        ocr_applied=should_run_ocr,
                        ocr_text=ocr_text,
                    ),
                )
            )

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
