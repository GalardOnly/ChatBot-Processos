from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol

import fitz


class OcrEngine(Protocol):
    def extract_page_text(self, page: fitz.Page, zoom: float = 2.0) -> str:
        """Extrai texto OCR de uma pagina renderizada."""


class RapidOcrEngine:
    def __init__(self) -> None:
        from rapidocr_onnxruntime import RapidOCR

        self._engine = RapidOCR()

    def extract_page_text(self, page: fitz.Page, zoom: float = 2.0) -> str:
        with TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "page.png"
            pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            pixmap.save(image_path)
            result, _elapsed = self._engine(str(image_path))

        if not result:
            return ""
        return "\n".join(str(item[1]) for item in result if len(item) >= 2)

