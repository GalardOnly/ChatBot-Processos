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


class SearchRequest(BaseModel):
    pergunta: str
    top_k: int = 5


class SearchSource(BaseModel):
    pagina: int
    chunk_index: int
    tipo_documento: str | None
    score: float
    trecho: str


class SearchResponse(BaseModel):
    processo_id: str
    pergunta: str
    fontes: list[SearchSource]


class ErrorResponse(BaseModel):
    error: str
    detail: str
