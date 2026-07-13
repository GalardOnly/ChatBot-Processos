from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import fitz

DEFAULT_SAMPLE_CHARS = 500
LOW_TEXT_THRESHOLD = 80
IMAGE_WITH_SPARSE_TEXT_THRESHOLD = 500


@dataclass(frozen=True)
class PageExtraction:
    page_number: int
    char_count: int
    word_count: int
    image_count: int
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
) -> PdfExtractionReport:
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF nao encontrado: {path}")
    if not path.is_file():
        raise ValueError(f"Caminho nao e arquivo: {path}")

    pages: list[PageExtraction] = []
    with fitz.open(path) as document:
        for page_index, page in enumerate(document):
            text = normalize_text(page.get_text("text"))
            image_count = len(page.get_images(full=True))
            pages.append(
                PageExtraction(
                    page_number=page_index + 1,
                    char_count=len(text),
                    word_count=len(text.split()),
                    image_count=image_count,
                    text_sample=text[:sample_chars],
                    is_probably_empty=_is_probably_empty(text),
                    quality_notes=_quality_notes(text, image_count=image_count),
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


def _quality_notes(text: str, image_count: int = 0) -> list[str]:
    if not text.strip():
        notes = ["sem_texto_extraido"]
        if image_count:
            notes.append("possivel_pagina_escaneada_ou_imagem")
        return notes
    if image_count and len(text) < IMAGE_WITH_SPARSE_TEXT_THRESHOLD:
        return ["imagem_com_texto_curto", "provavel_necessidade_de_ocr"]
    if len(text) < LOW_TEXT_THRESHOLD:
        return ["baixo_texto_extraido"]
    return ["texto_extraido"]
