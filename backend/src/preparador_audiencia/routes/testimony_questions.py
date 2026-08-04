from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.repositories import ChunkRepository, ProcessoRepository
from preparador_audiencia.schemas import (
    ErrorResponse,
    TestimonyQuestionGuideRequest,
    TestimonyQuestionGuideResponse,
)
from preparador_audiencia.structured_transcription import build_structured_transcription
from preparador_audiencia.structured_transcription_repository import (
    TRANSCRIPTION_SCHEMA_VERSION,
    StructuredTranscriptionRecord,
    StructuredTranscriptionRepository,
)
from preparador_audiencia.testimony_comparison import (
    TestimonyBodyUnavailableError,
    TestimonyNotFoundError,
    UnsafeTestimonyContentError,
)
from preparador_audiencia.testimony_comparison_repository import (
    TestimonyComparisonRepository,
)
from preparador_audiencia.testimony_questions import (
    TestimonyQuestionsUnavailableError,
    generate_testimony_questions,
)
from preparador_audiencia.testimony_questions_repository import (
    TestimonyQuestionGuideRecord,
    TestimonyQuestionGuideRepository,
)

router = APIRouter()


@router.post(
    "/processo/{processo_id}/depoimentos/{depoimento_id}/perguntas-audiencia",
    response_model=TestimonyQuestionGuideResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def create_testimony_question_guide(
    processo_id: str,
    depoimento_id: str,
    request: TestimonyQuestionGuideRequest,
) -> TestimonyQuestionGuideResponse | JSONResponse:
    if request.max_perguntas < 3 or request.max_perguntas > 15:
        return _error_response(
            400,
            "invalid_question_limit",
            "max_perguntas deve ficar entre 3 e 15.",
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
                "Aguarde o processamento completo antes de gerar perguntas.",
            )
        transcription = _current_transcription(connection, processo_id)
        comparisons = TestimonyComparisonRepository(connection).list_for_testimony(
            processo_id,
            depoimento_id,
        )
        try:
            record = generate_testimony_questions(
                processo_id,
                depoimento_id,
                transcription.schema_version,
                transcription.payload,
                comparisons,
                TestimonyQuestionGuideRepository(connection),
                max_questions=request.max_perguntas,
                regenerate=request.regenerar,
            )
        except TestimonyNotFoundError as exc:
            return _error_response(404, "testimony_not_found", str(exc))
        except TestimonyBodyUnavailableError as exc:
            return _error_response(409, "testimony_body_unavailable", str(exc))
        except UnsafeTestimonyContentError as exc:
            return _error_response(409, "unsafe_testimony_content", str(exc))
        except TestimonyQuestionsUnavailableError as exc:
            return _error_response(503, "llm_unavailable", str(exc))
        return _to_response(record)
    finally:
        connection.close()


@router.get(
    "/processo/{processo_id}/perguntas-audiencia/{roteiro_id}",
    response_model=TestimonyQuestionGuideResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_testimony_question_guide(
    processo_id: str,
    roteiro_id: str,
) -> TestimonyQuestionGuideResponse | JSONResponse:
    connection = connect_database()
    initialize_database(connection)
    try:
        if ProcessoRepository(connection).get(processo_id) is None:
            return _error_response(404, "process_not_found", "Processo nao encontrado.")
        record = TestimonyQuestionGuideRepository(connection).get(roteiro_id)
        if record is None or record.processo_id != processo_id:
            return _error_response(
                404,
                "question_guide_not_found",
                "Roteiro de perguntas nao encontrado.",
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


def _to_response(record: TestimonyQuestionGuideRecord) -> TestimonyQuestionGuideResponse:
    return TestimonyQuestionGuideResponse(
        roteiro_id=record.id,
        processo_id=record.processo_id,
        versao=record.schema_version,
        versao_transcricao=record.transcription_schema_version,
        modelo=record.model,
        fallback_usado=record.fallback_used,
        depoimento=record.payload["depoimento"],
        perguntas=record.payload.get("perguntas", []),
        pontos_para_confirmar=record.payload.get("pontos_para_confirmar", []),
        comparacoes_utilizadas=record.payload.get("comparacoes_utilizadas", []),
        avisos=record.payload.get("avisos", []),
        gerado_em=record.created_at,
        atualizado_em=record.updated_at,
    )


def _error_response(status_code: int, error: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=error, detail=detail).model_dump(),
    )
