from __future__ import annotations

from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, File, UploadFile
from fastapi.responses import JSONResponse

from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.ingestion import create_processo_from_pdf, process_pdf
from preparador_audiencia.repositories import ProcessoRepository
from preparador_audiencia.schemas import ErrorResponse, ProcessStatusResponse, UploadResponse

app = FastAPI(title="Preparador de Audiencia API", version="0.1.0")

MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def error_response(status_code: int, error: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=error, detail=detail).model_dump(),
    )


@app.post(
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


@app.get(
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

