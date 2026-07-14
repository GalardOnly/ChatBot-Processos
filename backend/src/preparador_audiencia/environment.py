from __future__ import annotations

from pathlib import Path


def load_environment(env_path: str | Path | None = None) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    path = Path(env_path) if env_path is not None else _default_env_path()
    load_dotenv(path, override=False)


def _default_env_path() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"
