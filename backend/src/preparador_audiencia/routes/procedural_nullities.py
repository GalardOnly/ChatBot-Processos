from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.legal_catalog import PROCEDURAL_NULLITY_TOPIC_IDS
from preparador_audiencia.nullity_analysis_repository import (
    NullityAnalysisRecord,
    NullityAnalysisRepository,
)
from preparador_audiencia.procedural_nullity_engine import (
    ProceduralNullityUnavailableError,
    generate_procedural_nullity,
)
from preparador_audiencia.repositories import ProcessoRepository
from preparador_audiencia.schemas import (
    ErrorResponse,
    ProceduralNullityBatchRequest,
    ProceduralNullityBatchResponse,
    ProceduralNullityGenerateRequest,
    ProceduralNullityResponse,
)

router = APIRouter()


@router.post(
    "/processo/{processo_id}/analise-nulidades/{tema_id}",
    response_model=ProceduralNullityResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def create_procedural_nullity(
    processo_id: str,
    tema_id: str,
    request: ProceduralNullityGenerateRequest,
) -> ProceduralNullityResponse | JSONResponse:
    validation = _validation_error(tema_id, request.top_k)
    if validation is not None:
        return validation
    connection = connect_database()
    initialize_database(connection)
    try:
        process_error = _ready_process_error(connection, processo_id)
        if process_error is not None:
            return process_error
        try:
            record = generate_procedural_nullity(
                processo_id,
                tema_id,
                NullityAnalysisRepository(connection),
                top_k=request.top_k,
                regenerate=request.regenerar,
            )
        except ProceduralNullityUnavailableError as exc:
            return _error_response(503, "llm_unavailable", str(exc))
        return _to_response(record)
    finally:
        connection.close()


@router.get(
    "/processo/{processo_id}/analise-nulidades/{tema_id}",
    response_model=ProceduralNullityResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def get_procedural_nullity(
    processo_id: str,
    tema_id: str,
) -> ProceduralNullityResponse | JSONResponse:
    validation = _validation_error(tema_id, 24)
    if validation is not None:
        return validation
    connection = connect_database()
    initialize_database(connection)
    try:
        if ProcessoRepository(connection).get(processo_id) is None:
            return _error_response(404, "process_not_found", "Processo nao encontrado.")
        record = NullityAnalysisRepository(connection).get(processo_id, tema_id)
        if record is None:
            return _error_response(
                404,
                "nullity_analysis_not_found",
                "A analise deste tema ainda nao foi gerada para o processo.",
            )
        return _to_response(record)
    finally:
        connection.close()


@router.post(
    "/processo/{processo_id}/analise-nulidades",
    response_model=ProceduralNullityBatchResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def create_procedural_nullities(
    processo_id: str,
    request: ProceduralNullityBatchRequest,
) -> ProceduralNullityBatchResponse | JSONResponse:
    if request.top_k < 12 or request.top_k > 40:
        return _invalid_top_k()
    topics = request.temas or list(PROCEDURAL_NULLITY_TOPIC_IDS)
    invalid = [topic for topic in topics if topic not in PROCEDURAL_NULLITY_TOPIC_IDS]
    if invalid:
        return _error_response(
            400,
            "invalid_nullity_topic",
            f"Tema de nulidade desconhecido: {invalid[0]}.",
        )
    topics = list(dict.fromkeys(topics))
    connection = connect_database()
    initialize_database(connection)
    try:
        process_error = _ready_process_error(connection, processo_id)
        if process_error is not None:
            return process_error
        repository = NullityAnalysisRepository(connection)
        records = []
        errors = []
        for topic_id in topics:
            try:
                records.append(
                    generate_procedural_nullity(
                        processo_id,
                        topic_id,
                        repository,
                        top_k=request.top_k,
                        regenerate=request.regenerar,
                    )
                )
            except ProceduralNullityUnavailableError as exc:
                errors.append(
                    {
                        "tema": topic_id,
                        "erro": "llm_unavailable",
                        "detalhe": str(exc),
                    }
                )
        status = "concluido" if not errors else "parcial" if records else "erro"
        return ProceduralNullityBatchResponse(
            processo_id=processo_id,
            status=status,
            analises=[_to_response(record) for record in records],
            erros=errors,
        )
    finally:
        connection.close()


@router.get(
    "/processo/{processo_id}/analise-nulidades",
    response_model=ProceduralNullityBatchResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_procedural_nullities(
    processo_id: str,
) -> ProceduralNullityBatchResponse | JSONResponse:
    connection = connect_database()
    initialize_database(connection)
    try:
        if ProcessoRepository(connection).get(processo_id) is None:
            return _error_response(404, "process_not_found", "Processo nao encontrado.")
        records = NullityAnalysisRepository(connection).list_for_process(processo_id)
        return ProceduralNullityBatchResponse(
            processo_id=processo_id,
            status="concluido",
            analises=[_to_response(record) for record in records],
            erros=[],
        )
    finally:
        connection.close()


def _to_response(record: NullityAnalysisRecord) -> ProceduralNullityResponse:
    payload = record.payload
    return ProceduralNullityResponse(
        processo_id=record.processo_id,
        tema=record.topic_id,
        titulo=payload.get("titulo", record.topic_id),
        escopo=payload.get("escopo", ""),
        conclusao=record.conclusion,
        conclusao_rotulo=payload.get("conclusao_rotulo", ""),
        confianca=payload.get("confianca", "baixa"),
        versao=record.schema_version,
        versao_catalogo=record.catalog_version,
        modelo=record.model,
        fallback_usado=record.fallback_used,
        modo_busca=record.search_mode,
        resumo=payload.get("resumo", ""),
        requisitos=payload.get("requisitos", []),
        providencias=payload.get("providencias", []),
        lacunas=payload.get("lacunas", []),
        fontes_processuais=payload.get("fontes_processuais", []),
        fontes_juridicas=payload.get("fontes_juridicas", []),
        avisos=payload.get("avisos", []),
        gerado_em=record.created_at,
        atualizado_em=record.updated_at,
    )


def _validation_error(tema_id: str, top_k: int) -> JSONResponse | None:
    if tema_id not in PROCEDURAL_NULLITY_TOPIC_IDS:
        return _error_response(
            400,
            "invalid_nullity_topic",
            f"Tema de nulidade desconhecido: {tema_id}.",
        )
    if top_k < 12 or top_k > 40:
        return _invalid_top_k()
    return None


def _ready_process_error(connection, processo_id: str) -> JSONResponse | None:
    process = ProcessoRepository(connection).get(processo_id)
    if process is None:
        return _error_response(404, "process_not_found", "Processo nao encontrado.")
    if process.status != "concluido":
        return _error_response(
            409,
            "process_not_ready",
            "Aguarde o processamento completo antes de analisar nulidades.",
        )
    return None


def _invalid_top_k() -> JSONResponse:
    return _error_response(400, "invalid_top_k", "top_k deve ficar entre 12 e 40.")


def _error_response(status_code: int, error: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=error, detail=detail).model_dump(),
    )
