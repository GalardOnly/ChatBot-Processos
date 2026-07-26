from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean

from preparador_audiencia.chat import ChatResult, answer_process_question
from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.evaluation import EvaluationCase
from preparador_audiencia.quality import LegalQualityEvaluation
from preparador_audiencia.repositories import (
    ChatMessageRepository,
    ChunkRepository,
    QualityEvaluationRepository,
)
from preparador_audiencia.retrieval import index_process_chunks_configured
from preparador_audiencia.search import SearchResult
from preparador_audiencia.settings import (
    embedding_provider_from_environment,
    evaluator_llm_from_environment,
    fallback_llm_from_environment,
    primary_llm_from_environment,
)


@dataclass(frozen=True)
class ResponseBenchmarkCaseResult:
    case_id: str
    pergunta: str
    resposta: str
    generator_model: str | None
    fallback_used: bool
    latency_ms: int | None
    source_pages: list[int]
    source_chunks: list[dict[str, object]]
    quality: LegalQualityEvaluation | None
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["quality"] = self.quality.to_dict() if self.quality else None
        return payload


@dataclass(frozen=True)
class ResponseBenchmarkReport:
    processo_id: str
    top_k: int
    generator_model: str
    fallback_model: str
    evaluator_model: str
    embedding_model: str
    indexed_chunks: int
    average_fidelidade_fontes: float
    average_completude_juridica: float
    average_utilidade_audiencia: float
    high_risk_count: int
    cases: list[ResponseBenchmarkCaseResult]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["cases"] = [case.to_dict() for case in self.cases]
        return payload


def run_response_quality_benchmark(
    processo_id: str,
    cases: list[EvaluationCase],
    *,
    top_k: int = 5,
    generator_model: str | None = None,
    fallback_model: str | None = None,
    evaluator_model: str | None = None,
    embedding_model: str | None = None,
    index_before_search: bool = True,
) -> ResponseBenchmarkReport:
    resolved_generator = generator_model or primary_llm_from_environment()
    resolved_fallback = fallback_model or fallback_llm_from_environment()
    resolved_evaluator = evaluator_model or evaluator_llm_from_environment()
    resolved_embedding = embedding_model or embedding_provider_from_environment()
    connection = connect_database()
    initialize_database(connection)
    chunks = ChunkRepository(connection)
    messages = ChatMessageRepository(connection)
    quality_evaluations = QualityEvaluationRepository(connection)

    try:
        indexed_chunks = (
            index_process_chunks_configured(processo_id, chunks, resolved_embedding)
            if index_before_search
            else chunks.count_for_processo(processo_id)
        )
        case_results = [
            _run_case(
                processo_id=processo_id,
                case=case,
                messages=messages,
                quality_evaluations=quality_evaluations,
                top_k=top_k,
                generator_model=resolved_generator,
                fallback_model=resolved_fallback,
                evaluator_model=resolved_evaluator,
            )
            for case in cases
        ]
    finally:
        connection.close()

    return ResponseBenchmarkReport(
        processo_id=processo_id,
        top_k=top_k,
        generator_model=resolved_generator,
        fallback_model=resolved_fallback,
        evaluator_model=resolved_evaluator,
        embedding_model=resolved_embedding,
        indexed_chunks=indexed_chunks,
        average_fidelidade_fontes=_average_quality(case_results, "fidelidade_fontes"),
        average_completude_juridica=_average_quality(case_results, "completude_juridica"),
        average_utilidade_audiencia=_average_quality(case_results, "utilidade_audiencia"),
        high_risk_count=sum(
            1
            for result in case_results
            if result.quality and result.quality.risco_alucinacao == "alto"
        ),
        cases=case_results,
    )


def write_response_benchmark_report(
    report: ResponseBenchmarkReport,
    output_path: str | Path,
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    path.with_suffix(".md").write_text(render_response_benchmark_markdown(report), encoding="utf-8")


def render_response_benchmark_markdown(report: ResponseBenchmarkReport) -> str:
    lines = [
        "# Benchmark de Respostas da PoC",
        "",
        f"Processo: `{report.processo_id}`",
        "",
        f"Gerador principal: `{report.generator_model}`",
        "",
        f"Fallback: `{report.fallback_model}`",
        "",
        f"Avaliador: `{report.evaluator_model}`",
        "",
        f"Recuperador: `{report.embedding_model}`",
        "",
        f"Chunks indexados: `{report.indexed_chunks}`",
        "",
        f"Top K: `{report.top_k}`",
        "",
        "## Medias",
        "",
        f"Fidelidade as fontes: `{report.average_fidelidade_fontes:.2f}/5`",
        "",
        f"Completude juridica: `{report.average_completude_juridica:.2f}/5`",
        "",
        f"Utilidade para audiencia: `{report.average_utilidade_audiencia:.2f}/5`",
        "",
        f"Casos com risco alto de alucinacao: `{report.high_risk_count}`",
        "",
        "## Casos",
        "",
        "| Caso | Modelo | Paginas | Fidelidade | Completude | Utilidade | Risco | Erro |",
        "|---|---|---|---:|---:|---:|---|---|",
    ]
    for result in report.cases:
        quality = result.quality
        lines.append(
            "| "
            f"`{result.case_id}` | "
            f"`{result.generator_model or 'nao gerado'}` | "
            f"{_format_pages(result.source_pages)} | "
            f"{quality.fidelidade_fontes if quality else ''} | "
            f"{quality.completude_juridica if quality else ''} | "
            f"{quality.utilidade_audiencia if quality else ''} | "
            f"{quality.risco_alucinacao if quality else ''} | "
            f"{result.error or (quality.error if quality and quality.error else '')} |"
        )
    for result in report.cases:
        quality = result.quality
        lines.extend(
            [
                "",
                f"### {result.case_id}",
                "",
                f"Pergunta: {result.pergunta}",
                "",
                f"Resposta: {result.resposta or 'Resposta nao gerada.'}",
                "",
                f"Veredito do avaliador: {quality.veredito if quality else 'Nao avaliado.'}",
            ]
        )
        if quality:
            lines.extend(
                [
                    "",
                    f"Pontos fortes: {_format_items(quality.pontos_fortes)}",
                    "",
                    f"Problemas: {_format_items(quality.problemas)}",
                    "",
                    f"Faltou: {_format_items(quality.faltou)}",
                ]
            )
    return "\n".join(lines) + "\n"


def _run_case(
    *,
    processo_id: str,
    case: EvaluationCase,
    messages: ChatMessageRepository,
    quality_evaluations: QualityEvaluationRepository,
    top_k: int,
    generator_model: str,
    fallback_model: str,
    evaluator_model: str,
) -> ResponseBenchmarkCaseResult:
    try:
        chat_result = answer_process_question(
            processo_id=processo_id,
            pergunta=case.pergunta,
            messages=messages,
            top_k=top_k,
            primary_model=generator_model,
            fallback_model=fallback_model,
            evaluate_quality=True,
            evaluator_model=evaluator_model,
            quality_evaluations=quality_evaluations,
        )
        return _case_result(case, chat_result)
    except Exception as exc:
        return ResponseBenchmarkCaseResult(
            case_id=case.id,
            pergunta=case.pergunta,
            resposta="",
            generator_model=None,
            fallback_used=False,
            latency_ms=None,
            source_pages=[],
            source_chunks=[],
            quality=None,
            error=str(exc),
        )


def _case_result(case: EvaluationCase, chat_result: ChatResult) -> ResponseBenchmarkCaseResult:
    return ResponseBenchmarkCaseResult(
        case_id=case.id,
        pergunta=case.pergunta,
        resposta=chat_result.resposta,
        generator_model=chat_result.modelo,
        fallback_used=chat_result.fallback_usado,
        latency_ms=None,
        source_pages=_unique_pages(chat_result.fontes),
        source_chunks=_source_chunks(chat_result.fontes),
        quality=chat_result.avaliacao,
        error=chat_result.erro,
    )


def _average_quality(results: list[ResponseBenchmarkCaseResult], field_name: str) -> float:
    values = [
        getattr(result.quality, field_name)
        for result in results
        if result.quality is not None and result.quality.error is None
    ]
    return round(mean(values), 4) if values else 0.0


def _unique_pages(sources: list[SearchResult]) -> list[int]:
    return sorted({source.page_number for source in sources})


def _source_chunks(sources: list[SearchResult]) -> list[dict[str, object]]:
    return [
        {
            "pagina": source.page_number,
            "chunk_index": source.chunk_index,
            "tipo_documento": source.document_type,
            "score": source.score,
        }
        for source in sources
    ]


def _format_pages(pages: list[int]) -> str:
    return ", ".join(f"p. {page}" for page in pages) if pages else ""


def _format_items(items: list[str]) -> str:
    return "; ".join(items) if items else "nenhum"
