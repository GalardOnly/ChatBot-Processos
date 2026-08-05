from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from preparador_audiencia.llm import LLMAnswer, llm_client_from_spec
from preparador_audiencia.prompt_security import partition_adversarial_sources
from preparador_audiencia.quality import LegalQualityEvaluation, evaluate_legal_quality
from preparador_audiencia.question_router import route_question
from preparador_audiencia.repositories import ChatMessageRepository, QualityEvaluationRepository
from preparador_audiencia.retrieval import (
    ROUTED_QUERY_WEIGHT,
    search_process_queries_configured,
    search_process_queries_lexical,
)
from preparador_audiencia.schemas import SearchSource
from preparador_audiencia.search import SearchResult
from preparador_audiencia.settings import (
    fallback_llm_from_environment,
    primary_llm_from_environment,
)

NO_SOURCES_ANSWER = (
    "Nao encontrei base suficiente no processo para responder com seguranca. "
    "Tente reformular a pergunta ou indicar o ponto do processo que deseja analisar."
)
LOW_CONFIDENCE_OCR_ANSWER = (
    "Encontrei evidencias apenas em paginas com extracao de baixa confianca "
    "ou ainda nao classificadas. "
    "Nao vou afirmar a resposta como fato. Confira diretamente {pages} no PDF "
    "ou reenvie uma copia mais legivel."
)
ADVERSARIAL_SOURCES_ANSWER = (
    "Os trechos recuperados contem instrucoes potencialmente adversariais e foram "
    "bloqueados. Nao ha outra fonte segura suficiente para responder. Confira {pages} "
    "diretamente no PDF."
)
LLM_UNAVAILABLE_ANSWER = (
    "Gemini e Groq estao indisponiveis no momento. Nenhuma resposta foi gerada. "
    "A pergunta ficou registrada e pode ser reenviada quando o servico normalizar."
)


@dataclass(frozen=True)
class ChatTimings:
    triagem_ms: int
    recuperacao_ms: int
    validacao_fontes_ms: int
    geracao_ms: int
    avaliacao_ms: int
    total_ms: int


@dataclass(frozen=True)
class ChatResult:
    pergunta: str
    resposta: str
    modelo: str | None
    fallback_usado: bool
    fontes: list[SearchResult]
    latency_ms: int | None = None
    tempos: ChatTimings | None = None
    avaliacao: LegalQualityEvaluation | None = None
    erro: str | None = None


def answer_process_question(
    processo_id: str,
    pergunta: str,
    messages: ChatMessageRepository,
    *,
    top_k: int = 5,
    primary_model: str | None = None,
    fallback_model: str | None = None,
    evaluate_quality: bool = False,
    evaluator_model: str | None = None,
    quality_evaluations: QualityEvaluationRepository | None = None,
    use_question_routing: bool = True,
    lexical_only: bool = False,
) -> ChatResult:
    total_started = perf_counter()
    messages.add(processo_id, "user", pergunta)

    routing_started = perf_counter()
    question_route = route_question(pergunta) if use_question_routing else None
    guide_query = question_route.guide_query() if question_route else ""
    routing_ms = _elapsed_ms(routing_started)

    search_queries = (
        search_process_queries_lexical
        if lexical_only
        else search_process_queries_configured
    )
    retrieval_started = perf_counter()
    retrieved_sources = search_queries(
        processo_id=processo_id,
        queries=[
            (pergunta, 1.0),
            (guide_query, ROUTED_QUERY_WEIGHT),
        ],
        top_k=top_k,
    )
    retrieval_ms = _elapsed_ms(retrieval_started)

    if not retrieved_sources:
        messages.add(
            processo_id,
            "assistant",
            NO_SOURCES_ANSWER,
            model="sistema",
            retrieved_pages=[],
            retrieved_chunks=[],
        )
        return ChatResult(
            pergunta=pergunta,
            resposta=NO_SOURCES_ANSWER,
            modelo="sistema",
            fallback_usado=False,
            fontes=[],
            tempos=_chat_timings(
                total_started,
                routing_ms=routing_ms,
                retrieval_ms=retrieval_ms,
            ),
        )

    validation_started = perf_counter()
    security_checked_sources, flagged_sources = partition_adversarial_sources(
        retrieved_sources
    )
    validation_ms = _elapsed_ms(validation_started)
    if not security_checked_sources:
        blocked_answer = ADVERSARIAL_SOURCES_ANSWER.format(
            pages=_page_references(
                [flagged.source for flagged in flagged_sources]
            )
        )
        messages.add(
            processo_id,
            "assistant",
            blocked_answer,
            model="sistema",
            retrieved_pages=_unique_pages(retrieved_sources),
            retrieved_chunks=_retrieved_chunks(retrieved_sources),
        )
        return ChatResult(
            pergunta=pergunta,
            resposta=blocked_answer,
            modelo="sistema",
            fallback_usado=False,
            fontes=[],
            tempos=_chat_timings(
                total_started,
                routing_ms=routing_ms,
                retrieval_ms=retrieval_ms,
                validation_ms=validation_ms,
            ),
        )

    confidence_started = perf_counter()
    sources = [
        source
        for source in security_checked_sources
        if source.source_confidence in {"alta", "media"}
    ]
    excluded_confidence_sources = [
        source
        for source in security_checked_sources
        if source.source_confidence not in {"alta", "media"}
    ]
    validation_ms += _elapsed_ms(confidence_started)
    if not sources:
        low_confidence_answer = LOW_CONFIDENCE_OCR_ANSWER.format(
            pages=_page_references(excluded_confidence_sources)
        )
        messages.add(
            processo_id,
            "assistant",
            low_confidence_answer,
            model="sistema",
            retrieved_pages=_unique_pages(excluded_confidence_sources),
            retrieved_chunks=_retrieved_chunks(excluded_confidence_sources),
        )
        return ChatResult(
            pergunta=pergunta,
            resposta=low_confidence_answer,
            modelo="sistema",
            fallback_usado=False,
            fontes=[],
            tempos=_chat_timings(
                total_started,
                routing_ms=routing_ms,
                retrieval_ms=retrieval_ms,
                validation_ms=validation_ms,
            ),
        )

    primary_spec = primary_model or primary_llm_from_environment()
    fallback_spec = fallback_model or fallback_llm_from_environment()
    generation_started = perf_counter()
    answer, fallback_used = _answer_with_fallback(
        question_route.llm_question() if question_route else pergunta,
        sources,
        primary_spec,
        fallback_spec,
    )
    generation_ms = _elapsed_ms(generation_started)

    if answer.error:
        messages.add(
            processo_id,
            "assistant",
            LLM_UNAVAILABLE_ANSWER,
            model="sistema",
            error=answer.error,
            retrieved_pages=_unique_pages(sources),
            retrieved_chunks=_retrieved_chunks(sources),
        )
        raise RuntimeError(answer.error)

    answer_text = _decorate_answer(
        answer.answer,
        pergunta=pergunta,
        flagged_pages=_unique_pages(
            [flagged.source for flagged in flagged_sources]
        ),
        excluded_confidence_pages=_unique_pages(excluded_confidence_sources),
    )
    evaluation = None
    evaluation_ms = 0
    if evaluate_quality:
        evaluation_started = perf_counter()
        evaluation = evaluate_legal_quality(
            pergunta=pergunta,
            resposta=answer_text,
            sources=sources,
            evaluator_model=evaluator_model,
        )
        if quality_evaluations is not None:
            quality_evaluations.add(
                processo_id=processo_id,
                pergunta=pergunta,
                resposta=answer_text,
                evaluation=evaluation,
                generator_model=answer.model,
            )
        evaluation_ms = _elapsed_ms(evaluation_started)

    messages.add(
        processo_id,
        "assistant",
        answer_text,
        model=answer.model,
        latency_ms=answer.latency_ms,
        retrieved_pages=_unique_pages(sources),
        retrieved_chunks=_retrieved_chunks(sources),
    )
    return ChatResult(
        pergunta=pergunta,
        resposta=answer_text,
        modelo=answer.model,
        fallback_usado=fallback_used,
        fontes=sources,
        latency_ms=answer.latency_ms,
        tempos=_chat_timings(
            total_started,
            routing_ms=routing_ms,
            retrieval_ms=retrieval_ms,
            validation_ms=validation_ms,
            generation_ms=generation_ms,
            evaluation_ms=evaluation_ms,
        ),
        avaliacao=evaluation,
    )


def _chat_timings(
    total_started: float,
    *,
    routing_ms: int,
    retrieval_ms: int,
    validation_ms: int = 0,
    generation_ms: int = 0,
    evaluation_ms: int = 0,
) -> ChatTimings:
    return ChatTimings(
        triagem_ms=routing_ms,
        recuperacao_ms=retrieval_ms,
        validacao_fontes_ms=validation_ms,
        geracao_ms=generation_ms,
        avaliacao_ms=evaluation_ms,
        total_ms=_elapsed_ms(total_started),
    )


def _elapsed_ms(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1000))


def _answer_with_fallback(
    pergunta: str,
    sources: list[SearchResult],
    primary_spec: str,
    fallback_spec: str,
) -> tuple[LLMAnswer, bool]:
    primary_answer = _try_answer(primary_spec, pergunta, sources)
    if primary_answer.answer and not primary_answer.error:
        return primary_answer, False

    fallback_answer = _try_answer(fallback_spec, pergunta, sources)
    if fallback_answer.answer and not fallback_answer.error:
        return fallback_answer, True

    primary_error = primary_answer.error or "resposta vazia"
    fallback_error = fallback_answer.error or "resposta vazia"
    return (
        LLMAnswer(
            model=fallback_answer.model,
            answer="",
            latency_ms=fallback_answer.latency_ms,
            error=f"Gemini falhou: {primary_error}; Groq falhou: {fallback_error}",
        ),
        True,
    )


def _try_answer(model_spec: str, pergunta: str, sources: list[SearchResult]) -> LLMAnswer:
    try:
        return llm_client_from_spec(model_spec).answer(pergunta, sources)
    except Exception as exc:
        return LLMAnswer(model=model_spec, answer="", latency_ms=0, error=str(exc))


def _unique_pages(sources: list[SearchResult]) -> list[int]:
    return sorted({source.page_number for source in sources})


def _retrieved_chunks(sources: list[SearchResult]) -> list[dict[str, object]]:
    return [
        {
            "pagina": source.page_number,
            "chunk_index": source.chunk_index,
            "tipo_documento": source.document_type,
            "score": source.score,
            "confianca_fonte": source.source_confidence,
            "motor_ocr": source.ocr_engine,
            "versao_ocr": source.ocr_engine_version,
            "dispositivo_ocr": source.ocr_device,
            "cache_ocr": source.ocr_cache_hit,
            "fallback_ocr": source.ocr_fallback_used,
        }
        for source in sources
    ]


def sources_to_schema(sources: list[SearchResult]) -> list[SearchSource]:
    return [
        SearchSource(
            pagina=source.page_number,
            chunk_index=source.chunk_index,
            tipo_documento=source.document_type,
            score=source.score,
            trecho=source.text,
            confianca_fonte=source.source_confidence,
            motor_ocr=source.ocr_engine,
            versao_ocr=source.ocr_engine_version,
            dispositivo_ocr=source.ocr_device,
            cache_ocr=source.ocr_cache_hit,
            fallback_ocr=source.ocr_fallback_used,
        )
        for source in sources
    ]


def _page_references(sources: list[SearchResult]) -> str:
    return ", ".join(f"[p. {page}]" for page in _unique_pages(sources))


def _decorate_answer(
    answer: str,
    *,
    pergunta: str,
    flagged_pages: list[int],
    excluded_confidence_pages: list[int],
) -> str:
    notices: list[str] = []
    if flagged_pages:
        references = ", ".join(f"[p. {page}]" for page in flagged_pages)
        notices.append(
            "Aviso de seguranca: trechos potencialmente adversariais foram "
            f"desconsiderados em {references}."
        )
    if excluded_confidence_pages:
        references = ", ".join(
            f"[p. {page}]" for page in excluded_confidence_pages
        )
        notices.append(
            "Aviso de extracao: fontes de baixa confianca ou ainda nao "
            f"classificadas foram desconsideradas em {references}."
        )
    if _requires_broad_coverage(pergunta):
        notices.append(
            "Limite de cobertura: esta resposta usa os trechos mais relevantes "
            "recuperados e nao garante uma leitura integral de todas as paginas."
        )
    return "\n\n".join([answer, *notices])


def _requires_broad_coverage(pergunta: str) -> bool:
    normalized = pergunta.lower()
    broad_phrases = (
        "processo inteiro",
        "todo o processo",
        "todos os fatos",
        "todas as provas",
        "todos os documentos",
        "resumo completo",
        "analise completa",
        "análise completa",
        "visao geral completa",
        "visão geral completa",
    )
    return any(phrase in normalized for phrase in broad_phrases)
