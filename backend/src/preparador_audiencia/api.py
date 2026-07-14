from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, UploadFile
from fastapi.responses import JSONResponse

from preparador_audiencia.chat import answer_process_question, sources_to_schema
from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.ingestion import create_processo_from_pdf, process_pdf
from preparador_audiencia.repositories import ChatMessageRepository, ProcessoRepository
from preparador_audiencia.schemas import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    ProcessListItem,
    ProcessListResponse,
    ProcessStatusResponse,
    SearchRequest,
    SearchResponse,
    UploadResponse,
)
from preparador_audiencia.search import search_process

router = APIRouter()

MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def error_response(status_code: int, error: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=error, detail=detail).model_dump(),
    )


@router.post(
    "/upload",
    response_model=UploadResponse,
    responses={400: {"model": ErrorResponse}, 413: {"model": ErrorResponse}},
)
async def upload_process_pdf(
    file: Annotated[UploadFile, File()],
    background_tasks: BackgroundTasks,
) -> UploadResponse | JSONResponse:
    if file.content_type not in {None, "application/pdf"}:
        return error_response(400, "invalid_file_type", "Envie um arquivo PDF.")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        return error_response(413, "file_too_large", "O PDF excede o limite de 50 MB.")
    if not content.startswith(b"%PDF"):
        return error_response(400, "invalid_pdf", "O arquivo enviado nao parece ser PDF.")

    processo_id = create_processo_from_pdf(file.filename or "processo.pdf", content)
    background_tasks.add_task(process_pdf, processo_id)
    return UploadResponse(processo_id=processo_id, status="pendente")


@router.get(
    "/processo/{processo_id}/status",
    response_model=ProcessStatusResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_process_status(processo_id: str) -> ProcessStatusResponse | JSONResponse:
    connection = connect_database()
    initialize_database(connection)
    processo = ProcessoRepository(connection).get(processo_id)
    if processo is None:
        return error_response(404, "process_not_found", "Processo nao encontrado.")
    return ProcessStatusResponse(
        processo_id=processo.id,
        status=processo.status,
        paginas_extraidas=processo.page_count,
        chunks=processo.chunk_count,
        erro=processo.error_message,
    )


@router.get("/processos", response_model=ProcessListResponse)
async def list_recent_processes(limit: int = 10) -> ProcessListResponse | JSONResponse:
    if limit <= 0 or limit > 50:
        return error_response(400, "invalid_limit", "limit deve ficar entre 1 e 50.")

    connection = connect_database()
    initialize_database(connection)
    processos = ProcessoRepository(connection).list_recent(limit)
    return ProcessListResponse(
        processos=[
            ProcessListItem(
                processo_id=processo.id,
                filename=processo.filename,
                status=processo.status,
                paginas_extraidas=processo.page_count,
                chunks=processo.chunk_count,
                criado_em=processo.created_at,
                atualizado_em=processo.updated_at,
            )
            for processo in processos
        ]
    )


@router.post(
    "/processo/{processo_id}/buscar",
    response_model=SearchResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def search_process_sources(
    processo_id: str,
    request: SearchRequest,
) -> SearchResponse | JSONResponse:
    pergunta = request.pergunta.strip()
    if not pergunta:
        return error_response(400, "empty_question", "Informe uma pergunta para buscar.")
    if request.top_k <= 0 or request.top_k > 20:
        return error_response(400, "invalid_top_k", "top_k deve ficar entre 1 e 20.")

    connection = connect_database()
    initialize_database(connection)
    processo = ProcessoRepository(connection).get(processo_id)
    if processo is None:
        return error_response(404, "process_not_found", "Processo nao encontrado.")
    if processo.status != "concluido":
        return error_response(
            409,
            "process_not_ready",
            "Aguarde o processamento do processo terminar antes de buscar.",
        )

    results = search_process(processo_id=processo_id, pergunta=pergunta, top_k=request.top_k)
    return SearchResponse(
        processo_id=processo_id,
        pergunta=pergunta,
        fontes=sources_to_schema(results),
    )


@router.post(
    "/processo/{processo_id}/chat",
    response_model=ChatResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def chat_with_process(
    processo_id: str,
    request: ChatRequest,
) -> ChatResponse | JSONResponse:
    pergunta = request.pergunta.strip()
    if not pergunta:
        return error_response(400, "empty_question", "Informe uma pergunta para o chat.")
    if request.top_k <= 0 or request.top_k > 20:
        return error_response(400, "invalid_top_k", "top_k deve ficar entre 1 e 20.")

    connection = connect_database()
    initialize_database(connection)
    processo = ProcessoRepository(connection).get(processo_id)
    if processo is None:
        return error_response(404, "process_not_found", "Processo nao encontrado.")
    if processo.status != "concluido":
        return error_response(
            409,
            "process_not_ready",
            "Aguarde o processamento do processo terminar antes de conversar.",
        )

    try:
        result = answer_process_question(
            processo_id=processo_id,
            pergunta=pergunta,
            messages=ChatMessageRepository(connection),
            top_k=request.top_k,
        )
    except RuntimeError as exc:
        return error_response(
            503,
            "llm_unavailable",
            f"Nao foi possivel gerar resposta com Gemini nem com Groq: {exc}",
        )

    return ChatResponse(
        processo_id=processo_id,
        pergunta=result.pergunta,
        resposta=result.resposta,
        modelo=result.modelo,
        fallback_usado=result.fallback_usado,
        fontes=sources_to_schema(result.fontes),
    )
