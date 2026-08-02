from __future__ import annotations

import os
from pathlib import Path

DEFAULT_STORAGE_DIR = "storage"
DEFAULT_CHROMA_DIR = "chroma"
DEFAULT_EMBEDDING_PROVIDER = "legal-ensemble"
DEFAULT_PRIMARY_LLM = "gemini:gemini-3-flash-preview"
DEFAULT_FALLBACK_LLM = "groq:llama-3.1-8b-instant"
DEFAULT_NULLITY_FALLBACK_LLM = "groq:llama-3.3-70b-versatile"
DEFAULT_EVALUATOR_LLM = "groq:llama-3.1-8b-instant"
DEFAULT_OCR_ZOOM = 1.5
DEFAULT_OCR_WORKERS = 2
DEFAULT_EMBEDDING_BATCH_SIZE = 16
DEFAULT_EMBEDDING_DEVICE = "auto"
DEFAULT_MAX_UPLOAD_MB = 200


def storage_dir_from_environment() -> Path:
    return Path(os.getenv("PREPARADOR_STORAGE_DIR", DEFAULT_STORAGE_DIR))


def chroma_dir_from_environment() -> Path:
    return Path(os.getenv("PREPARADOR_CHROMA_DIR", DEFAULT_CHROMA_DIR))


def primary_llm_from_environment() -> str:
    return os.getenv("PREPARADOR_PRIMARY_LLM", DEFAULT_PRIMARY_LLM)


def fallback_llm_from_environment() -> str:
    return os.getenv("PREPARADOR_FALLBACK_LLM", DEFAULT_FALLBACK_LLM)


def nullity_fallback_llm_from_environment() -> str:
    return os.getenv(
        "PREPARADOR_NULLITY_FALLBACK_LLM",
        DEFAULT_NULLITY_FALLBACK_LLM,
    )


def evaluator_llm_from_environment() -> str:
    return os.getenv("PREPARADOR_EVALUATOR_LLM", DEFAULT_EVALUATOR_LLM)


def embedding_provider_from_environment() -> str:
    return os.getenv("PREPARADOR_EMBEDDING_PROVIDER", DEFAULT_EMBEDDING_PROVIDER)


def ocr_zoom_from_environment() -> float:
    return max(1.0, float(os.getenv("PREPARADOR_OCR_ZOOM", str(DEFAULT_OCR_ZOOM))))


def ocr_workers_from_environment() -> int:
    return max(1, int(os.getenv("PREPARADOR_OCR_WORKERS", str(DEFAULT_OCR_WORKERS))))


def embedding_batch_size_from_environment() -> int:
    return max(
        1,
        int(
            os.getenv(
                "PREPARADOR_EMBEDDING_BATCH_SIZE",
                str(DEFAULT_EMBEDDING_BATCH_SIZE),
            )
        ),
    )


def embedding_device_from_environment() -> str:
    device = os.getenv(
        "PREPARADOR_EMBEDDING_DEVICE",
        DEFAULT_EMBEDDING_DEVICE,
    ).strip().lower()
    if device in {"auto", "cpu", "cuda"}:
        return device
    if device.startswith("cuda:") and device[5:].isdigit():
        return device
    raise ValueError(
        "PREPARADOR_EMBEDDING_DEVICE deve ser auto, cpu, cuda ou cuda:N."
    )


def max_upload_bytes_from_environment() -> int:
    max_upload_mb = max(
        1,
        int(os.getenv("PREPARADOR_MAX_UPLOAD_MB", str(DEFAULT_MAX_UPLOAD_MB))),
    )
    return max_upload_mb * 1024 * 1024
