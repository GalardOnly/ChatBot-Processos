from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.repositories import ChunkRepository, ProcessoRepository
from preparador_audiencia.schemas import (
    ErrorResponse,
    TestimonyComparisonRequest,
    TestimonyComparisonResponse,
)
from preparador_audiencia.structured_transcription import build_structured_transcription
from preparador_audiencia.structured_transcription_repository import (
    TRANSCRIPTION_SCHEMA_VERSION,
    StructuredTranscriptionRecord,
    StructuredTranscriptionRepository,
)
from preparador_audiencia.testimony_comparison import (
    TestimonyBodyUnavailableError,
    TestimonyComparisonUnavailableError,
    TestimonyNotFoundError,
    UnsafeTestimonyContentError,
    compare_testimonies,
)
from preparador_audiencia.testimony_comparison_repository import (
    TestimonyComparisonRecord,
    TestimonyComparisonRepository,
)

router = APIRouter()


@router.post(
    "/processo/{processo_id}/comparacao-depoimentos",
    response_model=TestimonyComparisonResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def create_testimony_comparison(
    processo_id: str,
    request: TestimonyComparisonRequest,
) -> TestimonyComparisonResponse | JSONResponse:
    if request.depoimento_a_id == request.depoimento_b_id:
        return _error_response(
            400,
            "same_testimony",
            "Selecione dois depoimentos diferentes para comparar.",
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
                "Aguarde o processamento completo antes de comparar depoimentos.",
            )
        transcription = _current_transcription(connection, processo_id)
        try:
            record = compare_testimonies(
                processo_id,
                request.depoimento_a_id,
                request.depoimento_b_id,
                transcription.schema_version,
                transcription.payload,
                TestimonyComparisonRepository(connection),
                regenerate=request.regenerar,
            )
        except TestimonyNotFoundError as exc:
            return _error_response(404, "testimony_not_found", str(exc))
        except TestimonyBodyUnavailableError as exc:
            return _error_response(409, "testimony_body_unavailable", str(exc))
        except UnsafeTestimonyContentError as exc:
            return _error_response(409, "unsafe_testimony_content", str(exc))
        except TestimonyComparisonUnavailableError as exc:
            return _error_response(503, "llm_unavailable", str(exc))
        return _to_response(record)
    finally:
        connection.close()


@router.get(
    "/processo/{processo_id}/comparacao-depoimentos/{comparison_id}",
    response_model=TestimonyComparisonResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_testimony_comparison(
    processo_id: str,
    comparison_id: str,
) -> TestimonyComparisonResponse | JSONResponse:
    connection = connect_database()
    initialize_database(connection)
    try:
        if ProcessoRepository(connection).get(processo_id) is None:
            return _error_response(404, "process_not_found", "Processo nao encontrado.")
        record = TestimonyComparisonRepository(connection).get(comparison_id)
        if record is None or record.processo_id != processo_id:
            return _error_response(
                404,
                "comparison_not_found",
                "Comparacao de depoimentos nao encontrada.",
            )
        return _to_response(record)
    finally:
        connection.close()


def _current_transcription(connection, processo_id: str) -> StructuredTranscriptionRecord:
    repository = StructuredTranscriptionRepository(connection)
    record = repository.get(processo_id)
    if record is not None and record.schema_version == TRANSCRIPTION_SCHEMA_VERSION:
        return record
    chunks = ChunkRepository(connection).list_for_processo(processo_id)
    result = build_structured_transcription(chunks)
    return repository.save(
        processo_id,
        status=result.status,
        payload={"depoimentos": result.testimonies, "avisos": result.warnings},
    )


def _to_response(record: TestimonyComparisonRecord) -> TestimonyComparisonResponse:
    return TestimonyComparisonResponse(
        comparacao_id=record.id,
        processo_id=record.processo_id,
        versao=record.schema_version,
        versao_transcricao=record.transcription_schema_version,
        modelo=record.model,
        fallback_usado=record.fallback_used,
        depoimento_a=record.payload["depoimento_a"],
        depoimento_b=record.payload["depoimento_b"],
        semelhancas=record.payload.get("semelhancas", []),
        contradicoes_potenciais=record.payload.get("contradicoes_potenciais", []),
        pontos_nao_comparaveis=record.payload.get("pontos_nao_comparaveis", []),
        avisos=record.payload.get("avisos", []),
        gerado_em=record.created_at,
        atualizado_em=record.updated_at,
    )


def _error_response(status_code: int, error: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=error, detail=detail).model_dump(),
    )
