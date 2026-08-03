from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.hearing_dossier import generate_hearing_dossier
from preparador_audiencia.hearing_dossier_repository import (
    HearingDossierRecord,
    HearingDossierRepository,
    HearingDossierSectionRecord,
)
from preparador_audiencia.repositories import ProcessoRepository
from preparador_audiencia.schemas import (
    DossierContradictionsSectionResponse,
    DossierKeyEventsSectionResponse,
    DossierSectionBase,
    DossierTestimoniesSectionResponse,
    ErrorResponse,
    HearingDossierGenerateRequest,
    HearingDossierResponse,
)

router = APIRouter()


@router.post(
    "/processo/{processo_id}/dossie-audiencia",
    response_model=HearingDossierResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def create_or_resume_hearing_dossier(
    processo_id: str,
    request: HearingDossierGenerateRequest,
) -> HearingDossierResponse | JSONResponse:
    if request.top_k < 8 or request.top_k > 30:
        return _error_response(
            400,
            "invalid_top_k",
            "top_k deve ficar entre 8 e 30 para o dossie de audiencia.",
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
                "Aguarde o processamento completo antes de gerar o dossie de audiencia.",
            )
        record = generate_hearing_dossier(
            processo_id,
            HearingDossierRepository(connection),
            top_k=request.top_k,
            regenerate=request.regenerar,
        )
        if record.status == "erro":
            return _error_response(
                503,
                "llm_unavailable",
                record.error_message or "Nao foi possivel gerar o dossie de audiencia.",
            )
        return _to_response(record)
    finally:
        connection.close()


@router.get(
    "/processo/{processo_id}/dossie-audiencia",
    response_model=HearingDossierResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_hearing_dossier(processo_id: str) -> HearingDossierResponse | JSONResponse:
    connection = connect_database()
    initialize_database(connection)
    try:
        if ProcessoRepository(connection).get(processo_id) is None:
            return _error_response(404, "process_not_found", "Processo nao encontrado.")
        record = HearingDossierRepository(connection).get(processo_id)
        if record is None:
            return _error_response(
                404,
                "dossier_not_found",
                "O dossie de audiencia ainda nao foi gerado para este processo.",
            )
        return _to_response(record)
    finally:
        connection.close()


def _to_response(record: HearingDossierRecord) -> HearingDossierResponse:
    sections = {section.key: section for section in record.sections}
    key_events = sections["marcos_essenciais"]
    testimonies = sections["depoimentos"]
    contradictions = sections["contradicoes"]
    return HearingDossierResponse(
        processo_id=record.processo_id,
        status=record.status,
        versao=record.schema_version,
        erro=record.error_message,
        criado_em=record.created_at,
        atualizado_em=record.updated_at,
        marcos_essenciais=DossierKeyEventsSectionResponse(
            **_section_values(key_events),
            itens=key_events.payload.get("itens", []),
            campos_para_confirmar=key_events.payload.get("campos_para_confirmar", []),
        ),
        depoimentos=DossierTestimoniesSectionResponse(
            **_section_values(testimonies),
            itens=testimonies.payload.get("itens", []),
            lacunas=testimonies.payload.get("lacunas", []),
        ),
        contradicoes=DossierContradictionsSectionResponse(
            **_section_values(contradictions),
            itens=contradictions.payload.get("itens", []),
            lacunas=contradictions.payload.get("lacunas", []),
        ),
    )


def _section_values(section: HearingDossierSectionRecord) -> dict[str, object]:
    return DossierSectionBase(
        status=section.status,
        modelo=section.model,
        fallback_usado=section.fallback_used,
        recuperacao_ms=section.retrieval_ms,
        geracao_ms=section.generation_ms,
        erro=section.error_message,
        atualizado_em=section.updated_at,
        avisos=section.payload.get("avisos", []),
    ).model_dump()


def _error_response(status_code: int, error: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=error, detail=detail).model_dump(),
    )
