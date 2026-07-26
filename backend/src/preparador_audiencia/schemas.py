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


class ProcessListItem(BaseModel):
    processo_id: str
    filename: str
    status: ProcessStatus
    paginas_extraidas: int
    chunks: int
    criado_em: str
    atualizado_em: str


class ProcessListResponse(BaseModel):
    processos: list[ProcessListItem]


class QuestionTemplateResponse(BaseModel):
    id: str
    titulo: str
    area: str
    audiencia: str
    objetivo: str
    pergunta: str
    quando_usar: str
    tags: list[str]
    prioridade: int


class QuestionTemplateListResponse(BaseModel):
    perguntas: list[QuestionTemplateResponse]


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


class ChatRequest(BaseModel):
    pergunta: str
    top_k: int = 5
    avaliar: bool = False
    avaliador_modelo: str | None = None


class QualityEvaluationResponse(BaseModel):
    modelo_avaliador: str
    fidelidade_fontes: int
    completude_juridica: int
    utilidade_audiencia: int
    risco_alucinacao: str
    pontos_fortes: list[str]
    problemas: list[str]
    faltou: list[str]
    veredito: str
    erro: str | None


class ChatResponse(BaseModel):
    processo_id: str
    pergunta: str
    resposta: str
    modelo: str | None
    fallback_usado: bool
    fontes: list[SearchSource]
    avaliacao: QualityEvaluationResponse | None = None


class ErrorResponse(BaseModel):
    error: str
    detail: str
