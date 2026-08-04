from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.defense_theses import (
    DefenseThesesUnavailableError,
    generate_defense_theses,
)
from preparador_audiencia.defense_theses_repository import (
    DefenseThesesRecord,
    DefenseThesesRepository,
)
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
    DefenseThesesGenerateRequest,
    DefenseThesesResponse,
    ErrorResponse,
)

router = APIRouter()


@router.post(
    "/processo/{processo_id}/teses-defensivas",
    response_model=DefenseThesesResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def create_defense_theses(
    processo_id: str,
    request: DefenseThesesGenerateRequest,
) -> DefenseThesesResponse | JSONResponse:
    if request.top_k < 12 or request.top_k > 50:
        return _error_response(400, "invalid_top_k", "top_k deve ficar entre 12 e 50.")
    if request.max_teses < 1 or request.max_teses > 13:
        return _error_response(
            400,
            "invalid_thesis_limit",
            "max_teses deve ficar entre 1 e 13.",
        )
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
                "Aguarde o processamento completo antes de analisar teses defensivas.",
            )
        judgment = _current_judgment_structure(connection, processo_id)
        try:
            record = generate_defense_theses(
                processo_id,
                DefenseThesesRepository(connection),
                judgment_payload=judgment.payload,
                top_k=request.top_k,
                max_theses=request.max_teses,
                regenerate=request.regenerar,
            )
        except DefenseThesesUnavailableError as exc:
            return _error_response(503, "llm_unavailable", str(exc))
        return _to_response(record)
    finally:
        connection.close()


@router.get(
    "/processo/{processo_id}/teses-defensivas",
    response_model=DefenseThesesResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_defense_theses(
    processo_id: str,
) -> DefenseThesesResponse | JSONResponse:
    connection = connect_database()
    initialize_database(connection)
    try:
        if ProcessoRepository(connection).get(processo_id) is None:
            return _error_response(404, "process_not_found", "Processo nao encontrado.")
        record = DefenseThesesRepository(connection).get(processo_id)
        if record is None:
            return _error_response(
                404,
                "defense_theses_not_found",
                "A analise de teses defensivas ainda nao foi gerada para este processo.",
            )
        return _to_response(record)
    finally:
        connection.close()


def _current_judgment_structure(
    connection,
    processo_id: str,
) -> JudgmentStructureRecord:
    repository = JudgmentStructureRepository(connection)
    record = repository.get(processo_id)
    if record is not None and record.schema_version == JUDGMENT_STRUCTURE_SCHEMA_VERSION:
        return record
    chunks = ChunkRepository(connection).list_for_processo(processo_id)
    result = build_judgment_structure(chunks)
    return repository.save(
        processo_id,
        status=result.status,
        payload={
            "decisoes": result.decisions,
            "transitos_em_julgado": result.final_judgments,
            "avisos": result.warnings,
        },
    )


def _to_response(record: DefenseThesesRecord) -> DefenseThesesResponse:
    return DefenseThesesResponse(
        processo_id=record.processo_id,
        status=record.status,
        versao=record.schema_version,
        versao_catalogo=record.catalog_version,
        modelo=record.model,
        fallback_usado=record.fallback_used,
        modo_busca=record.payload.get("modo_busca", "lexical"),
        teses=record.payload.get("teses", []),
        lacunas_gerais=record.payload.get("lacunas_gerais", []),
        fontes_juridicas=record.payload.get("fontes_juridicas", []),
        avisos=record.payload.get("avisos", []),
        gerado_em=record.created_at,
        atualizado_em=record.updated_at,
    )


def _error_response(status_code: int, error: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=error, detail=detail).model_dump(),
    )
