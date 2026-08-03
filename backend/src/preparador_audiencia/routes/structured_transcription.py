from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.repositories import ChunkRepository, ProcessoRepository
from preparador_audiencia.schemas import (
    ErrorResponse,
    StructuredTranscriptionGenerateRequest,
    StructuredTranscriptionResponse,
)
from preparador_audiencia.structured_transcription import (
    build_structured_transcription,
)
from preparador_audiencia.structured_transcription_repository import (
    StructuredTranscriptionRecord,
    StructuredTranscriptionRepository,
)

router = APIRouter()


@router.post(
    "/processo/{processo_id}/transcricao-depoimentos",
    response_model=StructuredTranscriptionResponse,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def create_structured_transcription(
    processo_id: str,
    request: StructuredTranscriptionGenerateRequest,
) -> StructuredTranscriptionResponse | JSONResponse:
    connection = connect_database()
    initialize_database(connection)
    try:
        processo = ProcessoRepository(connection).get(processo_id)
        if processo is None:
            return _error_response(404, "process_not_found", "Processo nao encontrado.")
        if processo.status != "concluido":
            return _error_response(
                409,
                "process_not_ready",
                "Aguarde o processamento completo antes de transcrever os depoimentos.",
            )

        repository = StructuredTranscriptionRepository(connection)
        cached = repository.get(processo_id)
        if cached is not None and not request.regenerar:
            return _to_response(cached)

        chunks = ChunkRepository(connection).list_for_processo(processo_id)
        if not chunks:
            return _error_response(
                409,
                "process_without_text",
                "O processo nao possui texto extraido para transcricao.",
            )
        result = build_structured_transcription(chunks)
        record = repository.save(
            processo_id,
            status=result.status,
            payload={
                "depoimentos": result.testimonies,
                "avisos": result.warnings,
            },
        )
        return _to_response(record)
    finally:
        connection.close()


@router.get(
    "/processo/{processo_id}/transcricao-depoimentos",
    response_model=StructuredTranscriptionResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_structured_transcription(
    processo_id: str,
) -> StructuredTranscriptionResponse | JSONResponse:
    connection = connect_database()
    initialize_database(connection)
    try:
        if ProcessoRepository(connection).get(processo_id) is None:
            return _error_response(404, "process_not_found", "Processo nao encontrado.")
        record = StructuredTranscriptionRepository(connection).get(processo_id)
        if record is None:
            return _error_response(
                404,
                "transcription_not_found",
                "A transcricao estruturada ainda nao foi gerada para este processo.",
            )
        return _to_response(record)
    finally:
        connection.close()


def _to_response(record: StructuredTranscriptionRecord) -> StructuredTranscriptionResponse:
    return StructuredTranscriptionResponse(
        processo_id=record.processo_id,
        status=record.status,
        versao=record.schema_version,
        depoimentos=record.payload.get("depoimentos", []),
        avisos=record.payload.get("avisos", []),
        gerado_em=record.created_at,
        atualizado_em=record.updated_at,
    )


def _error_response(status_code: int, error: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=error, detail=detail).model_dump(),
    )
