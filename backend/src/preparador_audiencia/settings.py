from __future__ import annotations

import os
from pathlib import Path

DEFAULT_STORAGE_DIR = "storage"


def storage_dir_from_environment() -> Path:
    return Path(os.getenv("PREPARADOR_STORAGE_DIR", DEFAULT_STORAGE_DIR))

