from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, UploadFile
from fastapi.responses import JSONResponse

from preparador_audiencia.chat import ChatTimings, answer_process_question, sources_to_schema
from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.ingestion import (
    create_processo_from_staged_pdf,
    process_pdf,
    resolve_process_file_path,
)
from preparador_audiencia.lexical_search import search_process_lexical
from preparador_audiencia.nullity_analysis import analyze_recognition_nullity
from preparador_audiencia.question_bank import list_question_templates
from preparador_audiencia.repositories import (
    ChatMessageRepository,
    ChunkRepository,
    ProcessoRecord,
    ProcessoRepository,
    QualityEvaluationRepository,
)
from preparador_audiencia.retrieval import search_process_configured
from preparador_audiencia.schemas import (
    ChatRequest,
    ChatResponse,
    ChatTimingResponse,
    ErrorResponse,
    LegalSourceResponse,
    NullityAnalysisRequest,
    NullityAnalysisResponse,
    NullityRequirementResponse,
    ProcessListItem,
    ProcessListResponse,
    ProcessStatusResponse,
    QualityEvaluationResponse,
    QuestionTemplateListResponse,
    QuestionTemplateResponse,
    ReprocessResponse,
    SearchMode,
    SearchRequest,
    SearchResponse,
    UploadResponse,
)
from preparador_audiencia.settings import (
    max_upload_bytes_from_environment,
    storage_dir_from_environment,
)

router = APIRouter()

UPLOAD_CHUNK_BYTES = 1024 * 1024


def _process_search_mode(processo: ProcessoRecord) -> SearchMode:
    if processo.status == "concluido":
        return "hibrida"
    if processo.chunk_count > 0 and processo.progress_stage in {"indexando", "erro"}:
        return "lexical"
    return "indisponivel"


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

    max_upload_bytes = max_upload_bytes_from_environment()
    staged_path, digest, upload_error = await _stage_upload(file, max_upload_bytes)
    if upload_error is not None:
        return upload_error

    try:
        submission = create_processo_from_staged_pdf(
            file.filename or "processo.pdf",
            staged_path,
            digest,
        )
    except Exception:
        staged_path.unlink(missing_ok=True)
        raise
    if submission.should_process:
        background_tasks.add_task(process_pdf, submission.processo_id)
    return UploadResponse(
        processo_id=submission.processo_id,
        status=submission.status,
        reutilizado=submission.reused,
    )


async def _stage_upload(
    file: UploadFile,
    max_upload_bytes: int,
) -> tuple[Path, str, JSONResponse | None]:
    storage_dir = storage_dir_from_environment()
    storage_dir.mkdir(parents=True, exist_ok=True)
    digest = sha256()
    total_bytes = 0
    staged_path: Path | None = None
    upload_error: JSONResponse | None = None

    try:
        with NamedTemporaryFile(
            mode="wb",
            prefix=".upload-",
            suffix=".pdf",
            dir=storage_dir,
            delete=False,
        ) as destination:
            staged_path = Path(destination.name)
            first_chunk = True
            while chunk := await file.read(UPLOAD_CHUNK_BYTES):
                if first_chunk and not chunk.startswith(b"%PDF"):
                    upload_error = error_response(
                        400,
                        "invalid_pdf",
                        "O arquivo enviado nao parece ser PDF.",
                    )
                    break
                first_chunk = False
                total_bytes += len(chunk)
                if total_bytes > max_upload_bytes:
                    max_upload_mb = max_upload_bytes // (1024 * 1024)
                    upload_error = error_response(
                        413,
                        "file_too_large",
                        f"O PDF excede o limite local de {max_upload_mb} MB.",
                    )
                    break
                digest.update(chunk)
                destination.write(chunk)
    except Exception:
        if staged_path is not None:
            staged_path.unlink(missing_ok=True)
        raise

    if upload_error is not None:
        if staged_path is not None:
            staged_path.unlink(missing_ok=True)
        return staged_path or storage_dir / ".upload-invalido.pdf", "", upload_error

    if staged_path is None or total_bytes == 0:
        if staged_path is not None:
            staged_path.unlink(missing_ok=True)
        return (
            staged_path or storage_dir / ".upload-vazio.pdf",
            "",
            error_response(400, "invalid_pdf", "O PDF enviado esta vazio."),
        )
    return staged_path, digest.hexdigest(), None


@router.get(
    "/processo/{processo_id}/status",
    response_model=ProcessStatusResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_process_status(processo_id: str) -> ProcessStatusResponse | JSONResponse:
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
    search_mode = _process_search_mode(processo)
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
        reprocessamento_necessario=ChunkRepository(
            connection
        ).has_unknown_confidence(processo_id),
        consulta_disponivel=search_mode != "indisponivel",
        modo_busca=search_mode,
    )


@router.post(
    "/processo/{processo_id}/reprocessar",
    response_model=ReprocessResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def reprocess_process(
    processo_id: str,
    background_tasks: BackgroundTasks,
) -> ReprocessResponse | JSONResponse:
    connection = connect_database()
    initialize_database(connection)
    processos = ProcessoRepository(connection)
    processo = processos.get(processo_id)
    if processo is None:
        return error_response(404, "process_not_found", "Processo nao encontrado.")
    if processo.status in {"pendente", "processando"}:
        return error_response(
            409,
            "process_already_running",
            "O processo ja esta na fila ou em processamento.",
        )
    if not resolve_process_file_path(processo.file_path).is_file():
        return error_response(
            409,
            "source_file_missing",
            "O PDF original nao esta disponivel para reprocessamento.",
        )

    processos.mark_pending_for_reprocessing(processo_id)
    background_tasks.add_task(process_pdf, processo_id)
    return ReprocessResponse(
        processo_id=processo_id,
        status="pendente",
        mensagem="Reprocessamento iniciado.",
    )


@router.get("/processos", response_model=ProcessListResponse)
def list_recent_processes(limit: int = 10) -> ProcessListResponse | JSONResponse:
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
def list_hearing_questions(
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
def search_process_sources(
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
    search_mode = _process_search_mode(processo)
    if search_mode == "indisponivel":
        return error_response(
            409,
            "process_not_ready",
            "Aguarde a extracao e a organizacao do texto terminarem antes de buscar.",
        )

    if search_mode == "lexical":
        results = search_process_lexical(
            processo_id=processo_id,
            pergunta=pergunta,
            top_k=request.top_k,
        )
    else:
        results = search_process_configured(
            processo_id=processo_id,
            pergunta=pergunta,
            top_k=request.top_k,
        )
    return SearchResponse(
        processo_id=processo_id,
        pergunta=pergunta,
        modo_busca=search_mode,
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
def chat_with_process(
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
    search_mode = _process_search_mode(processo)
    if search_mode == "indisponivel":
        return error_response(
            409,
            "process_not_ready",
            "Aguarde a extracao e a organizacao do texto terminarem antes de conversar.",
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
            lexical_only=search_mode == "lexical",
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
        modo_busca=search_mode,
        fontes=sources_to_schema(result.fontes),
        tempos=_chat_timings_to_schema(result.tempos),
        avaliacao=_quality_to_schema(result.avaliacao),
    )


@router.post(
    "/processo/{processo_id}/analise-nulidade/reconhecimento",
    response_model=NullityAnalysisResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def analyze_recognition_for_process(
    processo_id: str,
    request: NullityAnalysisRequest,
) -> NullityAnalysisResponse | JSONResponse:
    if request.top_k <= 0 or request.top_k > 20:
        return error_response(400, "invalid_top_k", "top_k deve ficar entre 1 e 20.")

    connection = connect_database()
    initialize_database(connection)
    processo = ProcessoRepository(connection).get(processo_id)
    if processo is None:
        return error_response(404, "process_not_found", "Processo nao encontrado.")
    search_mode = _process_search_mode(processo)
    if search_mode == "indisponivel":
        return error_response(
            409,
            "process_not_ready",
            "Aguarde a organizacao do texto antes de analisar possiveis nulidades.",
        )

    try:
        result = analyze_recognition_nullity(
            processo_id,
            top_k=request.top_k,
            lexical_only=search_mode == "lexical",
        )
    except RuntimeError as exc:
        return error_response(
            503,
            "llm_unavailable",
            f"Nao foi possivel concluir a analise com Gemini nem com Groq: {exc}",
        )

    return NullityAnalysisResponse(
        processo_id=processo_id,
        tema=result.topic,
        titulo=result.title,
        conclusao=result.conclusion,
        conclusao_rotulo=result.conclusion_label,
        confianca=result.confidence,
        resumo=result.summary,
        aplicabilidade=result.applicability,
        justificativa_aplicabilidade=result.applicability_summary,
        impacto_processual=result.procedural_impact,
        justificativa_impacto=result.impact_summary,
        paginas_impacto=list(result.impact_pages),
        requisitos=[
            NullityRequirementResponse(
                id=item.id,
                categoria=item.category,
                titulo=item.label,
                condicao=item.condition,
                resultado=item.result,
                justificativa=item.justification,
                paginas=list(item.pages),
                fontes_juridicas=list(item.legal_source_ids),
            )
            for item in result.requirements
        ],
        providencias=list(result.next_steps),
        lacunas=list(result.gaps),
        modelo=result.model,
        fallback_usado=result.fallback_used,
        modo_busca=search_mode,
        fontes_processuais=sources_to_schema(list(result.process_sources)),
        fontes_juridicas=[
            LegalSourceResponse(
                id=source.id,
                titulo=source.title,
                autoridade=source.authority,
                tipo=source.kind,
                referencia=source.reference,
                url=source.url,
            )
            for source in result.legal_sources
        ],
        versao_catalogo_juridico=result.legal_catalog_version,
        catalogo_verificado_em=result.legal_catalog_verified_at,
        avisos=list(result.warnings),
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


def _chat_timings_to_schema(timings: ChatTimings | None) -> ChatTimingResponse | None:
    if timings is None:
        return None
    return ChatTimingResponse(
        triagem_ms=timings.triagem_ms,
        recuperacao_ms=timings.recuperacao_ms,
        validacao_fontes_ms=timings.validacao_fontes_ms,
        geracao_ms=timings.geracao_ms,
        avaliacao_ms=timings.avaliacao_ms,
        total_ms=timings.total_ms,
    )
