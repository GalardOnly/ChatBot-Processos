from __future__ import annotations

import os
from pathlib import Path

DEFAULT_STORAGE_DIR = "storage"
DEFAULT_CHROMA_DIR = "chroma"
DEFAULT_PRIMARY_LLM = "gemini:gemini-3-flash-preview"
DEFAULT_FALLBACK_LLM = "groq:llama-3.1-8b-instant"


def storage_dir_from_environment() -> Path:
    return Path(os.getenv("PREPARADOR_STORAGE_DIR", DEFAULT_STORAGE_DIR))


def chroma_dir_from_environment() -> Path:
    return Path(os.getenv("PREPARADOR_CHROMA_DIR", DEFAULT_CHROMA_DIR))


def primary_llm_from_environment() -> str:
    return os.getenv("PREPARADOR_PRIMARY_LLM", DEFAULT_PRIMARY_LLM)


def fallback_llm_from_environment() -> str:
    return os.getenv("PREPARADOR_FALLBACK_LLM", DEFAULT_FALLBACK_LLM)
