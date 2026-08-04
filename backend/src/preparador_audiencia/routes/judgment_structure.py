from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.judgment_structure import (
    JUDGMENT_STRUCTURE_SCHEMA_VERSION,
    build_judgment_structure,
)
from preparador_audiencia.judgment_structure_repository import (
    JudgmentStructureRecord,
    JudgmentStructureRepository,
)
from preparador_audiencia.repositories import ChunkRepository, ProcessoRepository
from preparador_audiencia.schemas import (
    ErrorResponse,
    JudgmentStructureGenerateRequest,
    JudgmentStructureResponse,
)

router = APIRouter()


@router.post(
    "/processo/{processo_id}/estrutura-sentenca",
    response_model=JudgmentStructureResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def create_judgment_structure(
    processo_id: str,
    request: JudgmentStructureGenerateRequest,
) -> JudgmentStructureResponse | JSONResponse:
    connection = connect_database()
    initialize_database(connection)
    try:
        error = _ready_process_error(ProcessoRepository(connection), processo_id)
        if error is not None:
            return error
        repository = JudgmentStructureRepository(connection)
        cached = repository.get(processo_id)
        if (
            cached is not None
            and cached.schema_version == JUDGMENT_STRUCTURE_SCHEMA_VERSION
            and not request.regenerar
        ):
            return _to_response(cached)
        return _generate_and_save(
            processo_id,
            repository,
            ChunkRepository(connection),
        )
    finally:
        connection.close()


@router.get(
    "/processo/{processo_id}/estrutura-sentenca",
    response_model=JudgmentStructureResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_judgment_structure(
    processo_id: str,
) -> JudgmentStructureResponse | JSONResponse:
    connection = connect_database()
    initialize_database(connection)
    try:
        if ProcessoRepository(connection).get(processo_id) is None:
            return _error_response(404, "process_not_found", "Processo nao encontrado.")
        record = JudgmentStructureRepository(connection).get(processo_id)
        if record is None:
            return _error_response(
                404,
                "judgment_structure_not_found",
                "A estrutura de sentenca ainda nao foi gerada para este processo.",
            )
        return _to_response(record)
    finally:
        connection.close()


def _generate_and_save(
    processo_id: str,
    repository: JudgmentStructureRepository,
    chunks: ChunkRepository,
) -> JudgmentStructureResponse | JSONResponse:
    stored_chunks = chunks.list_for_processo(processo_id)
    if not stored_chunks:
        return _error_response(
            409,
            "process_without_text",
            "O processo nao possui texto extraido para estruturar a sentenca.",
        )
    result = build_judgment_structure(stored_chunks)
    record = repository.save(
        processo_id,
        status=result.status,
        payload={
            "decisoes": result.decisions,
            "transitos_em_julgado": result.final_judgments,
            "avisos": result.warnings,
        },
    )
    return _to_response(record)


def _to_response(record: JudgmentStructureRecord) -> JudgmentStructureResponse:
    return JudgmentStructureResponse(
        processo_id=record.processo_id,
        status=record.status,
        versao=record.schema_version,
        decisoes=record.payload.get("decisoes", []),
        transitos_em_julgado=record.payload.get("transitos_em_julgado", []),
        avisos=record.payload.get("avisos", []),
        gerado_em=record.created_at,
        atualizado_em=record.updated_at,
    )


def _ready_process_error(
    repository: ProcessoRepository,
    processo_id: str,
) -> JSONResponse | None:
    processo = repository.get(processo_id)
    if processo is None:
        return _error_response(404, "process_not_found", "Processo nao encontrado.")
    if processo.status != "concluido":
        return _error_response(
            409,
            "process_not_ready",
            "Aguarde o processamento completo antes de estruturar a sentenca.",
        )
    return None


def _error_response(status_code: int, error: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=error, detail=detail).model_dump(),
    )
