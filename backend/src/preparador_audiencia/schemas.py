from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

ProcessStatus = Literal["pendente", "processando", "concluido", "erro"]


class UploadResponse(BaseModel):
    processo_id: str
    status: ProcessStatus


class ProcessStatusResponse(BaseModel):
    processo_id: str
    status: ProcessStatus
    paginas_extraidas: int
    chunks: int
    erro: str | None


class ErrorResponse(BaseModel):
    error: str
    detail: str

