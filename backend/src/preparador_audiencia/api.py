from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, UploadFile
from fastapi.responses import JSONResponse

from preparador_audiencia.chat import answer_process_question, sources_to_schema
from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.ingestion import create_processo_from_pdf, process_pdf
from preparador_audiencia.question_bank import list_question_templates
from preparador_audiencia.repositories import (
    ChatMessageRepository,
    ProcessoRepository,
    QualityEvaluationRepository,
)
from preparador_audiencia.retrieval import search_process_configured
from preparador_audiencia.schemas import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    ProcessListItem,
    ProcessListResponse,
    ProcessStatusResponse,
    QualityEvaluationResponse,
    QuestionTemplateListResponse,
    QuestionTemplateResponse,
    SearchRequest,
    SearchResponse,
    UploadResponse,
)

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

    submission = create_processo_from_pdf(file.filename or "processo.pdf", content)
    if submission.should_process:
        background_tasks.add_task(process_pdf, submission.processo_id)
    return UploadResponse(
        processo_id=submission.processo_id,
        status=submission.status,
        reutilizado=submission.reused,
    )


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
    progress_percent = (
        round((processo.progress_current / processo.progress_total) * 100)
        if processo.progress_total
        else 0
    )
    if processo.status == "concluido":
        progress_percent = 100
    return ProcessStatusResponse(
        processo_id=processo.id,
        status=processo.status,
        paginas_extraidas=processo.page_count,
        chunks=processo.chunk_count,
        etapa=processo.progress_stage,
        progresso_atual=processo.progress_current,
        progresso_total=processo.progress_total,
        progresso_percentual=max(0, min(100, progress_percent)),
        mensagem=processo.progress_message,
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


@router.get("/perguntas-audiencia", response_model=QuestionTemplateListResponse)
async def list_hearing_questions(
    area: str | None = None,
    audiencia: str | None = None,
    tag: str | None = None,
    limit: int | None = None,
) -> QuestionTemplateListResponse | JSONResponse:
    if limit is not None and (limit <= 0 or limit > 100):
        return error_response(400, "invalid_limit", "limit deve ficar entre 1 e 100.")

    templates = list_question_templates(
        area=area,
        audiencia=audiencia,
        tags=[tag] if tag else None,
        limit=limit,
    )
    return QuestionTemplateListResponse(
        perguntas=[
            QuestionTemplateResponse(
                id=template.id,
                titulo=template.titulo,
                area=template.area,
                audiencia=template.audiencia,
                objetivo=template.objetivo,
                pergunta=template.pergunta,
                quando_usar=template.quando_usar,
                tags=template.tags,
                prioridade=template.prioridade,
            )
            for template in templates
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

    results = search_process_configured(
        processo_id=processo_id,
        pergunta=pergunta,
        top_k=request.top_k,
    )
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
            evaluate_quality=request.avaliar,
            evaluator_model=request.avaliador_modelo,
            quality_evaluations=QualityEvaluationRepository(connection)
            if request.avaliar
            else None,
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
        avaliacao=_quality_to_schema(result.avaliacao),
    )


def _quality_to_schema(evaluation) -> QualityEvaluationResponse | None:
    if evaluation is None:
        return None
    return QualityEvaluationResponse(
        modelo_avaliador=evaluation.evaluator_model,
        fidelidade_fontes=evaluation.fidelidade_fontes,
        completude_juridica=evaluation.completude_juridica,
        utilidade_audiencia=evaluation.utilidade_audiencia,
        risco_alucinacao=evaluation.risco_alucinacao,
        pontos_fortes=evaluation.pontos_fortes,
        problemas=evaluation.problemas,
        faltou=evaluation.faltou,
        veredito=evaluation.veredito,
        erro=evaluation.error,
    )
