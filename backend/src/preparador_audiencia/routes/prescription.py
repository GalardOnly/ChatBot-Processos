from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.prescription import (
    InterruptiveMilestone,
    InvalidPrescriptionInput,
    OffensePrescriptionInput,
    PrescriptionCalculationInput,
    SourceReference,
    SuspensionPeriod,
    calculate_prescription,
)
from preparador_audiencia.prescription_dates import extract_prescription_data
from preparador_audiencia.prescription_repository import (
    PrescriptionCalculationRecord,
    PrescriptionCalculationRepository,
)
from preparador_audiencia.repositories import ChunkRepository, ProcessoRepository
from preparador_audiencia.schemas import (
    ErrorResponse,
    PrescriptionCalculationRequest,
    PrescriptionCalculationResponse,
    PrescriptionDataResponse,
)

router = APIRouter()


@router.get(
    "/processo/{processo_id}/prescricao/dados",
    response_model=PrescriptionDataResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def get_prescription_data(
    processo_id: str,
) -> PrescriptionDataResponse | JSONResponse:
    connection = connect_database()
    initialize_database(connection)
    try:
        error = _ready_process_error(ProcessoRepository(connection), processo_id)
        if error is not None:
            return error
        chunks = ChunkRepository(connection).list_for_processo(processo_id)
        if not chunks:
            return _error_response(
                409,
                "process_without_text",
                "O processo nao possui texto extraido para localizar as datas.",
            )
        result = extract_prescription_data(chunks)
        return PrescriptionDataResponse(
            processo_id=processo_id,
            versao="1.0",
            datas=[
                {
                    "id": item.id,
                    "tipo_evento": item.event_type,
                    "rotulo": item.label,
                    "natureza": item.nature,
                    "data": item.value,
                    "valor_original": item.raw_value,
                    "pagina": item.page_number,
                    "chunk_index": item.chunk_index,
                    "trecho": item.excerpt,
                    "confianca_fonte": item.source_confidence,
                    "confianca_candidato": item.confidence,
                    "revisao_necessaria": item.review_required,
                }
                for item in result.dates
            ],
            delitos=[
                {
                    "id": item.id,
                    "artigo": item.article,
                    "pena_maxima_meses": item.maximum_penalty_months,
                    "pagina": item.page_number,
                    "chunk_index": item.chunk_index,
                    "trecho": item.excerpt,
                    "confianca_fonte": item.source_confidence,
                    "revisao_necessaria": item.review_required,
                }
                for item in result.offenses
            ],
            campos_ausentes=result.missing_fields,
            avisos=result.warnings,
        )
    finally:
        connection.close()


@router.post(
    "/processo/{processo_id}/prescricao/calcular",
    response_model=PrescriptionCalculationResponse,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def create_prescription_calculation(
    processo_id: str,
    request: PrescriptionCalculationRequest,
) -> PrescriptionCalculationResponse | JSONResponse:
    connection = connect_database()
    initialize_database(connection)
    try:
        error = _ready_process_error(ProcessoRepository(connection), processo_id)
        if error is not None:
            return error
        try:
            result = calculate_prescription(_to_domain_input(request))
        except InvalidPrescriptionInput as exc:
            return _error_response(422, "invalid_prescription_data", str(exc))
        input_payload = request.model_dump(mode="json")
        result_payload = _result_payload(result)
        record = PrescriptionCalculationRepository(connection).save(
            processo_id,
            input_payload=input_payload,
            result_payload=result_payload,
        )
        return _to_response(record)
    finally:
        connection.close()


@router.get(
    "/processo/{processo_id}/prescricao/calculos/{calculo_id}",
    response_model=PrescriptionCalculationResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_prescription_calculation(
    processo_id: str,
    calculo_id: str,
) -> PrescriptionCalculationResponse | JSONResponse:
    connection = connect_database()
    initialize_database(connection)
    try:
        if ProcessoRepository(connection).get(processo_id) is None:
            return _error_response(404, "process_not_found", "Processo nao encontrado.")
        record = PrescriptionCalculationRepository(connection).get(calculo_id)
        if record is None or record.processo_id != processo_id:
            return _error_response(
                404,
                "prescription_calculation_not_found",
                "Calculo de prescricao nao encontrado para este processo.",
            )
        return _to_response(record)
    finally:
        connection.close()


def _to_domain_input(request: PrescriptionCalculationRequest) -> PrescriptionCalculationInput:
    return PrescriptionCalculationInput(
        reference_date=request.data_referencia,
        defendant_name=request.reu,
        defendant_birth_date=request.data_nascimento_reu,
        sentence_status=request.situacao_sentenca,
        conviction_sentence_date=request.data_sentenca_condenatoria,
        offenses=tuple(
            OffensePrescriptionInput(
                offense_id=item.id,
                description=item.descricao,
                article=item.artigo,
                maximum_penalty_months=item.pena_maxima_meses,
                initial_term_type=item.tipo_termo_inicial,
                initial_term_date=item.data_termo_inicial,
                fact_date=item.data_fato,
                sexual_violence_against_woman=item.violencia_sexual_contra_mulher,
                interruptive_milestones=tuple(
                    InterruptiveMilestone(
                        event_type=milestone.tipo,
                        event_date=milestone.data,
                        source=SourceReference(milestone.pagina, milestone.trecho),
                    )
                    for milestone in item.marcos_interruptivos
                ),
                suspension_periods=tuple(
                    SuspensionPeriod(
                        suspension_type=period.tipo,
                        start_date=period.inicio,
                        end_date=period.fim,
                        source=SourceReference(period.pagina, period.trecho),
                    )
                    for period in item.periodos_suspensao
                ),
            )
            for item in request.delitos
        ),
    )


def _result_payload(result) -> dict[str, object]:
    return {
        "status": result.status,
        "data_referencia": result.calculated_at_date.isoformat(),
        "versao_calculo": result.calculation_version,
        "versao_regras_juridicas": result.legal_ruleset_version,
        "delitos": [
            {
                "id": item.offense_id,
                "descricao": item.description,
                "artigo": item.article,
                "status": item.status,
                "prazo_base_meses": item.base_period_months,
                "prazo_aplicado_meses": item.applied_period_months,
                "redutor_art_115_aplicado": item.article_115_reduction_applied,
                "motivos_redutor_art_115": list(item.article_115_reasons),
                "prazo_final": item.final_deadline.isoformat()
                if item.final_deadline is not None
                else None,
                "dias_ate_prazo": item.days_to_deadline,
                "intervalos": [
                    {
                        "inicio": interval.start_date.isoformat(),
                        "prazo_final": interval.deadline.isoformat(),
                        "fim_avaliado": interval.end_date.isoformat(),
                        "motivo_fim": interval.end_reason,
                        "status": interval.status,
                        "dias_suspensos": interval.suspended_days,
                    }
                    for interval in item.intervals
                ],
                "campos_ausentes": list(item.missing_fields),
                "avisos": list(item.warnings),
            }
            for item in result.offenses
        ],
        "fontes_juridicas": [
            {"id": source["id"], "titulo": source["title"], "url": source["url"]}
            for source in result.legal_sources
        ],
        "avisos": list(result.warnings),
    }


def _to_response(record: PrescriptionCalculationRecord) -> PrescriptionCalculationResponse:
    return PrescriptionCalculationResponse(
        calculo_id=record.id,
        processo_id=record.processo_id,
        gerado_em=record.created_at,
        atualizado_em=record.updated_at,
        **record.result_payload,
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
            "Aguarde o processamento completo antes de analisar a prescricao.",
        )
    return None


def _error_response(status_code: int, error: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=error, detail=detail).model_dump(),
    )
