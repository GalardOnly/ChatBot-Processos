from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import local
from typing import Protocol

import fitz


class OcrEngine(Protocol):
    def extract_page_text(self, page: fitz.Page, zoom: float = 2.0) -> str:
        """Extrai texto OCR de uma pagina renderizada."""


class RapidOcrEngine:
    def __init__(
        self,
        *,
        intra_op_num_threads: int = 4,
        inter_op_num_threads: int = 1,
    ) -> None:
        from rapidocr_onnxruntime import RapidOCR

        self._engine = RapidOCR(
            intra_op_num_threads=max(1, intra_op_num_threads),
            inter_op_num_threads=max(1, inter_op_num_threads),
        )

    def extract_page_text(self, page: fitz.Page, zoom: float = 2.0) -> str:
        return self.extract_image_text(self.render_page_image(page, zoom))

    def extract_image_text(self, image: bytes) -> str:
        result, _elapsed = self._engine(image)
        if not result:
            return ""
        return "\n".join(str(item[1]) for item in result if len(item) >= 2)

    @staticmethod
    def render_page_image(page: fitz.Page, zoom: float) -> bytes:
        pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return pixmap.tobytes("png")


class RapidOcrPool:
    def __init__(self, workers: int) -> None:
        self.workers = max(1, workers)
        self._executor = ThreadPoolExecutor(max_workers=self.workers)
        self._thread_state = local()

    def extract_images(self, images: list[bytes]) -> list[str]:
        return list(self._executor.map(self._extract_with_thread_engine, images))

    def close(self) -> None:
        self._executor.shutdown(wait=True)

    def _extract_with_thread_engine(self, image: bytes) -> str:
        engine = getattr(self._thread_state, "engine", None)
        if engine is None:
            engine = RapidOcrEngine(intra_op_num_threads=2, inter_op_num_threads=1)
            self._thread_state.engine = engine
        return engine.extract_image_text(image)
