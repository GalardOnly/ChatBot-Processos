from __future__ import annotations

from dataclasses import dataclass

from preparador_audiencia.llm import LLMAnswer, llm_client_from_spec
from preparador_audiencia.quality import LegalQualityEvaluation, evaluate_legal_quality
from preparador_audiencia.question_router import route_question
from preparador_audiencia.repositories import ChatMessageRepository, QualityEvaluationRepository
from preparador_audiencia.retrieval import (
    ROUTED_QUERY_WEIGHT,
    search_process_queries_configured,
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


@dataclass(frozen=True)
class ChatResult:
    pergunta: str
    resposta: str
    modelo: str | None
    fallback_usado: bool
    fontes: list[SearchResult]
    latency_ms: int | None = None
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
) -> ChatResult:
    messages.add(processo_id, "user", pergunta)
    question_route = route_question(pergunta) if use_question_routing else None
    search_query = question_route.search_query() if question_route else pergunta
    sources = search_process_queries_configured(
        processo_id=processo_id,
        queries=[
            (pergunta, 1.0),
            (search_query, ROUTED_QUERY_WEIGHT),
        ],
        top_k=top_k,
    )

    if not sources:
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
        )

    primary_spec = primary_model or primary_llm_from_environment()
    fallback_spec = fallback_model or fallback_llm_from_environment()
    answer, fallback_used = _answer_with_fallback(
        question_route.llm_question() if question_route else pergunta,
        sources,
        primary_spec,
        fallback_spec,
    )

    if answer.error:
        raise RuntimeError(answer.error)

    evaluation = None
    if evaluate_quality:
        evaluation = evaluate_legal_quality(
            pergunta=pergunta,
            resposta=answer.answer,
            sources=sources,
            evaluator_model=evaluator_model,
        )
        if quality_evaluations is not None:
            quality_evaluations.add(
                processo_id=processo_id,
                pergunta=pergunta,
                resposta=answer.answer,
                evaluation=evaluation,
                generator_model=answer.model,
            )

    messages.add(
        processo_id,
        "assistant",
        answer.answer,
        model=answer.model,
        latency_ms=answer.latency_ms,
        retrieved_pages=_unique_pages(sources),
        retrieved_chunks=_retrieved_chunks(sources),
    )
    return ChatResult(
        pergunta=pergunta,
        resposta=answer.answer,
        modelo=answer.model,
        fallback_usado=fallback_used,
        fontes=sources,
        latency_ms=answer.latency_ms,
        avaliacao=evaluation,
    )


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
        )
        for source in sources
    ]
