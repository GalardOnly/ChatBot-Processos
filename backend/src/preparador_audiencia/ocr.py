from __future__ import annotations

import json
import sys
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from io import BytesIO
from pathlib import Path
from threading import Lock, local
from typing import Protocol
from uuid import uuid4

import fitz

EasyOcrBox = Sequence[Sequence[float]]
EasyOcrResult = tuple[EasyOcrBox, str, float]
OCR_CACHE_SCHEMA_VERSION = "2"


@dataclass(frozen=True)
class OcrResult:
    text: str
    engine: str | None
    engine_version: str | None
    device: str | None
    cache_hit: bool = False
    fallback_used: bool = False
    warning: str | None = None


class OcrEngine(Protocol):
    def extract_page_text(self, page: fitz.Page, zoom: float = 2.0) -> str:
        """Extrai texto OCR de uma pagina renderizada."""


class BatchOcrEngine(Protocol):
    def extract_pages(self, pages: list[fitz.Page], zoom: float) -> list[OcrResult]:
        """Extrai OCR em lote e devolve a proveniencia de cada pagina."""


class RapidOcrEngine:
    name = "rapidocr"
    device = "cpu"

    def __init__(
        self,
        *,
        intra_op_num_threads: int = 4,
        inter_op_num_threads: int = 1,
    ) -> None:
        from rapidocr_onnxruntime import RapidOCR

        self.engine_version = _package_version("rapidocr-onnxruntime")
        self._engine = RapidOCR(
            intra_op_num_threads=max(1, intra_op_num_threads),
            inter_op_num_threads=max(1, inter_op_num_threads),
        )

    def extract_page_text(self, page: fitz.Page, zoom: float = 2.0) -> str:
        return self.extract_image(RapidOcrEngine.render_page_image(page, zoom)).text

    def extract_pages(self, pages: list[fitz.Page], zoom: float) -> list[OcrResult]:
        return [
            self.extract_image(RapidOcrEngine.render_page_image(page, zoom))
            for page in pages
        ]

    def extract_image(self, image: bytes) -> OcrResult:
        result, _elapsed = self._engine(image)
        text = ""
        if result:
            text = "\n".join(str(item[1]) for item in result if len(item) >= 2)
        return OcrResult(
            text=text,
            engine=self.name,
            engine_version=self.engine_version,
            device=self.device,
        )

    def extract_image_text(self, image: bytes) -> str:
        return self.extract_image(image).text

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


class EasyOcrEngine:
    name = "easyocr"

    def __init__(
        self,
        *,
        device: str = "auto",
        allow_model_download: bool = False,
        model_dir: str | Path | None = None,
        module_dir: str | Path | None = None,
        batch_size: int = 1,
    ) -> None:
        if module_dir is not None:
            resolved_module_dir = str(Path(module_dir).expanduser().resolve())
            if resolved_module_dir not in sys.path:
                sys.path.insert(0, resolved_module_dir)
        try:
            import easyocr
            import numpy as np
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("EasyOCR nao esta instalado no ambiente.") from exc

        use_gpu = _use_gpu(device)
        self.device = "gpu" if use_gpu else "cpu"
        self.engine_version = _package_version("easyocr")
        self.batch_size = max(1, batch_size)
        self._np = np
        self._image_type = Image
        self._reader = easyocr.Reader(
            ["pt", "en"],
            gpu=use_gpu,
            model_storage_directory=str(model_dir) if model_dir else None,
            download_enabled=allow_model_download,
            verbose=False,
        )
        self._lock = Lock()

    def extract_page_text(self, page: fitz.Page, zoom: float = 3.0) -> str:
        image = RapidOcrEngine.render_page_image(page, zoom)
        return self.extract_images([image])[0].text

    def extract_pages(self, pages: list[fitz.Page], zoom: float) -> list[OcrResult]:
        images = [RapidOcrEngine.render_page_image(page, zoom) for page in pages]
        return self.extract_images(images)

    def extract_images(self, images: list[bytes]) -> list[OcrResult]:
        if not images:
            return []
        opened = [self._image_type.open(BytesIO(image)).convert("RGB") for image in images]
        grouped: dict[tuple[int, int], list[int]] = {}
        for index, image in enumerate(opened):
            grouped.setdefault(image.size, []).append(index)

        texts = [""] * len(images)
        with self._lock:
            for _size, indexes in grouped.items():
                arrays = [self._np.asarray(opened[index]) for index in indexes]
                if self.batch_size == 1:
                    results = [
                        self._reader.readtext(array, detail=1, paragraph=False)
                        for array in arrays
                    ]
                else:
                    results = self._read_batched(arrays)
                for index, result in zip(indexes, results, strict=True):
                    texts[index] = easyocr_text_without_marginal_artifacts(
                        result,
                        image_width=opened[index].width,
                    )
        return [
            OcrResult(
                text=text,
                engine=self.name,
                engine_version=self.engine_version,
                device=self.device,
            )
            for text in texts
        ]

    def _read_batched(self, arrays: list[object]) -> list[list[EasyOcrResult]]:
        results: list[list[EasyOcrResult]] = []
        for start in range(0, len(arrays), self.batch_size):
            batch = arrays[start : start + self.batch_size]
            if len(batch) == 1:
                results.append(
                    self._reader.readtext(batch[0], detail=1, paragraph=False)
                )
                continue
            results.extend(
                self._reader.readtext_batched(
                    batch,
                    detail=1,
                    paragraph=False,
                    batch_size=len(batch),
                )
            )
        return results


class ManagedOcrEngine:
    def __init__(
        self,
        *,
        provider: str,
        device: str,
        allow_model_download: bool,
        model_dir: str | Path | None,
        module_dir: str | Path | None,
        cache_dir: str | Path,
        batch_size: int,
        primary_factory: Callable[[], object] | None = None,
        fallback_factory: Callable[[], object] | None = None,
    ) -> None:
        self.provider = provider
        self.device = device
        self.allow_model_download = allow_model_download
        self.model_dir = str(model_dir) if model_dir else None
        self.module_dir = str(module_dir) if module_dir else None
        _activate_module_dir(self.module_dir)
        self.cache_dir = Path(cache_dir)
        self.batch_size = max(1, batch_size)
        self._primary_factory = primary_factory
        self._fallback_factory = fallback_factory or RapidOcrEngine
        self._primary: object | None = None
        self._fallback: object | None = None
        self._engine_lock = Lock()

    def extract_page_text(self, page: fitz.Page, zoom: float = 3.0) -> str:
        return self.extract_pages([page], zoom)[0].text

    def extract_pages(self, pages: list[fitz.Page], zoom: float) -> list[OcrResult]:
        images = [RapidOcrEngine.render_page_image(page, zoom) for page in pages]
        return self.extract_images(images, zoom=zoom)

    def extract_images(self, images: list[bytes], *, zoom: float) -> list[OcrResult]:
        results: list[OcrResult | None] = [None] * len(images)
        missing_indexes: list[int] = []
        cache_keys: list[str] = []
        for index, image in enumerate(images):
            cache_key = self._cache_key(image, zoom)
            cache_keys.append(cache_key)
            cached = self._read_cache(cache_key)
            if cached is None:
                missing_indexes.append(index)
            else:
                results[index] = replace(cached, cache_hit=True)

        if missing_indexes:
            missing_images = [images[index] for index in missing_indexes]
            extracted = self._extract_missing(missing_images)
            for index, result in zip(missing_indexes, extracted, strict=True):
                results[index] = result
                self._write_cache(cache_keys[index], result)
        return [result or _empty_ocr_result() for result in results]

    def _extract_missing(self, images: list[bytes]) -> list[OcrResult]:
        primary_error: Exception | None = None
        try:
            primary = self._load_primary()
            primary_results = _extract_images_from_engine(primary, images)
        except Exception as exc:
            primary_error = exc
            primary_results = [_empty_ocr_result()] * len(images)

        fallback_indexes = [
            index for index, result in enumerate(primary_results) if not result.text.strip()
        ]
        if not fallback_indexes or self.provider == "rapidocr":
            return primary_results

        fallback_images = [images[index] for index in fallback_indexes]
        fallback = self._load_fallback()
        fallback_results = _extract_images_from_engine(fallback, fallback_images)
        warning = _safe_fallback_warning(primary_error)
        for index, fallback_result in zip(
            fallback_indexes,
            fallback_results,
            strict=True,
        ):
            primary_results[index] = replace(
                fallback_result,
                fallback_used=True,
                warning=warning,
            )
        return primary_results

    def _load_primary(self) -> object:
        with self._engine_lock:
            if self._primary is not None:
                return self._primary
            if self._primary_factory is not None:
                self._primary = self._primary_factory()
            elif self.provider == "rapidocr":
                self._primary = RapidOcrEngine()
            else:
                self._primary = EasyOcrEngine(
                    device=self.device,
                    allow_model_download=self.allow_model_download,
                    model_dir=self.model_dir,
                    module_dir=self.module_dir,
                    batch_size=self.batch_size,
                )
            return self._primary

    def _load_fallback(self) -> object:
        with self._engine_lock:
            if self._fallback is None:
                self._fallback = self._fallback_factory()
            return self._fallback

    def _cache_key(self, image: bytes, zoom: float) -> str:
        signature = "|".join(
            (
                OCR_CACHE_SCHEMA_VERSION,
                self.provider,
                self.device,
                str(zoom),
                _package_version("easyocr") or "easyocr-ausente",
                _package_version("rapidocr-onnxruntime") or "rapidocr-ausente",
                self.model_dir or "sem-diretorio",
                str(self.batch_size),
            )
        ).encode("utf-8")
        return sha256(signature + b"\0" + image).hexdigest()

    def _read_cache(self, cache_key: str) -> OcrResult | None:
        path = self.cache_dir / f"{cache_key}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return OcrResult(**payload)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def _write_cache(self, cache_key: str, result: OcrResult) -> None:
        path = self.cache_dir / f"{cache_key}.json"
        temporary = self.cache_dir / f".{cache_key}-{uuid4().hex}.tmp"
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps(asdict(result), ensure_ascii=False),
                encoding="utf-8",
            )
            temporary.replace(path)
        except OSError:
            temporary.unlink(missing_ok=True)


def easyocr_text_without_marginal_artifacts(
    results: Sequence[EasyOcrResult],
    image_width: int,
) -> str:
    readable: list[str] = []
    left_limit = image_width * 0.05
    right_limit = image_width * 0.95
    for box, text, _confidence in results:
        center_x = sum(float(point[0]) for point in box) / len(box)
        if center_x <= left_limit or center_x >= right_limit:
            continue
        if text.strip():
            readable.append(text)
    return "\n".join(readable)


def get_configured_ocr_engine() -> ManagedOcrEngine:
    from preparador_audiencia.settings import (
        easyocr_batch_size_from_environment,
        easyocr_model_dir_from_environment,
        easyocr_module_dir_from_environment,
        ocr_allow_model_download_from_environment,
        ocr_cache_dir_from_environment,
        ocr_device_from_environment,
        ocr_engine_from_environment,
    )

    return _configured_ocr_engine(
        ocr_engine_from_environment(),
        ocr_device_from_environment(),
        ocr_allow_model_download_from_environment(),
        easyocr_model_dir_from_environment(),
        easyocr_module_dir_from_environment(),
        str(ocr_cache_dir_from_environment()),
        easyocr_batch_size_from_environment(),
    )


@lru_cache(maxsize=8)
def _configured_ocr_engine(
    provider: str,
    device: str,
    allow_model_download: bool,
    model_dir: str | None,
    module_dir: str | None,
    cache_dir: str,
    batch_size: int,
) -> ManagedOcrEngine:
    return ManagedOcrEngine(
        provider=provider,
        device=device,
        allow_model_download=allow_model_download,
        model_dir=model_dir,
        module_dir=module_dir,
        cache_dir=cache_dir,
        batch_size=batch_size,
    )


def clear_configured_ocr_engine_cache() -> None:
    _configured_ocr_engine.cache_clear()


def _extract_images_from_engine(engine: object, images: list[bytes]) -> list[OcrResult]:
    extract_images = getattr(engine, "extract_images", None)
    if callable(extract_images):
        raw_results = extract_images(images)
        return [_coerce_result(engine, result) for result in raw_results]
    extract_image = getattr(engine, "extract_image", None)
    if callable(extract_image):
        return [_coerce_result(engine, extract_image(image)) for image in images]
    extract_image_text = getattr(engine, "extract_image_text", None)
    if callable(extract_image_text):
        return [_coerce_result(engine, extract_image_text(image)) for image in images]
    raise TypeError("Motor OCR nao oferece extracao por imagem.")


def _coerce_result(engine: object, result: object) -> OcrResult:
    if isinstance(result, OcrResult):
        return result
    return OcrResult(
        text=str(result or ""),
        engine=str(getattr(engine, "name", engine.__class__.__name__.lower())),
        engine_version=_optional_text(getattr(engine, "engine_version", None)),
        device=_optional_text(getattr(engine, "device", None)),
    )


def _empty_ocr_result() -> OcrResult:
    return OcrResult(text="", engine=None, engine_version=None, device=None)


def _package_version(package: str) -> str | None:
    try:
        return version(package)
    except PackageNotFoundError:
        return None


def _activate_module_dir(module_dir: str | None) -> None:
    if module_dir is None:
        return
    resolved = str(Path(module_dir).expanduser().resolve())
    if resolved not in sys.path:
        sys.path.insert(0, resolved)


def _use_gpu(device: str) -> bool:
    normalized = device.strip().lower()
    if normalized == "cpu":
        return False
    if normalized in {"gpu", "cuda"}:
        return True
    try:
        import torch

        return bool(torch.cuda.is_available())
    except ImportError:
        return False


def _safe_fallback_warning(error: Exception | None) -> str:
    if error is None:
        return "easyocr_sem_texto"
    return f"easyocr_indisponivel:{error.__class__.__name__}"


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
