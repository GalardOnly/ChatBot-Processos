from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from statistics import mean

import fitz
import httpx

from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.evaluation import EvaluationCase
from preparador_audiencia.ingestion import create_processo_from_pdf, process_pdf
from preparador_audiencia.reference_suite import (
    ReferenceCase,
    ReferenceProcess,
    ReferenceSuite,
)
from preparador_audiencia.repositories import ProcessoRecord, ProcessoRepository
from preparador_audiencia.routing_benchmark import (
    RoutingBenchmarkReport,
    run_routing_benchmark,
)
from preparador_audiencia.settings import embedding_provider_from_environment

DEFAULT_INCLUDED_STATUSES = frozenset({"pending", "in_review", "approved"})
DocumentFetcher = Callable[[str], bytes]


@dataclass(frozen=True)
class PreparedReferenceProcess:
    reference_id: str
    domain: str
    processo_id: str
    document: str
    page_count: int
    chunk_count: int
    reused: bool


@dataclass(frozen=True)
class ReferenceProcessBenchmark:
    reference_id: str
    domain: str
    processo_id: str
    document: str
    page_count: int
    chunk_count: int
    reused: bool
    review_status_counts: dict[str, int]
    routing: RoutingBenchmarkReport


@dataclass(frozen=True)
class ReferenceBenchmarkReport:
    suite_id: str
    embedding_model: str
    top_k: int
    total_processes: int
    total_cases: int
    review_status_counts: dict[str, int]
    raw_hit_rate: float
    routed_hit_rate: float
    raw_mrr: float
    routed_mrr: float
    improved_cases: int
    degraded_cases: int
    tied_cases: int
    processes: list[ReferenceProcessBenchmark]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def ensure_reference_document(
    process: ReferenceProcess,
    samples_root: str | Path,
    *,
    download_missing: bool = False,
    fetcher: DocumentFetcher | None = None,
) -> Path:
    root = Path(samples_root)
    target = root / process.document
    if not target.is_file():
        if not download_missing:
            raise FileNotFoundError(
                f"PDF de referencia nao encontrado: {target}. "
                "Use --download-missing para baixar a fonte registrada."
            )
        if not process.source_url:
            raise ValueError(f"Processo {process.id} nao possui source_url")
        content = (fetcher or _download_bytes)(process.source_url)
        if not content.startswith(b"%PDF"):
            raise ValueError(f"Fonte de {process.id} nao retornou um PDF valido")
        root.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    content = target.read_bytes()
    if not content.startswith(b"%PDF"):
        raise ValueError(f"Arquivo de {process.id} nao e um PDF valido: {target}")
    binary_digest = sha256(content).hexdigest()
    binary_matches = process.sha256 is None or binary_digest == process.sha256
    if process.text_sha256:
        text_digest = pdf_text_sha256(content)
        if text_digest != process.text_sha256:
            raise ValueError(
                f"SHA-256 textual divergente para {process.id}: esperado "
                f"{process.text_sha256}, obtido {text_digest}"
            )
    elif not binary_matches:
        raise ValueError(
            f"SHA-256 divergente para {process.id}: esperado "
            f"{process.sha256}, obtido {binary_digest}"
        )
    return target


def pdf_text_sha256(content: bytes) -> str:
    with fitz.open(stream=content, filetype="pdf") as document:
        pages = [
            " ".join(document.load_page(index).get_text("text").split())
            for index in range(document.page_count)
        ]
    canonical_text = "\n\f\n".join(pages).encode("utf-8")
    return sha256(canonical_text).hexdigest()


def prepare_reference_process(
    process: ReferenceProcess,
    samples_root: str | Path,
    *,
    download_missing: bool = False,
    fetcher: DocumentFetcher | None = None,
) -> PreparedReferenceProcess:
    path = ensure_reference_document(
        process,
        samples_root,
        download_missing=download_missing,
        fetcher=fetcher,
    )
    submission = create_processo_from_pdf(path.name, path.read_bytes())
    if submission.should_process:
        process_pdf(submission.processo_id)
    record = _load_process_record(submission.processo_id)
    if record.status != "concluido":
        raise RuntimeError(
            f"Processamento de {process.id} terminou com status {record.status}"
        )
    return PreparedReferenceProcess(
        reference_id=process.id,
        domain=process.domain,
        processo_id=record.id,
        document=process.document,
        page_count=record.page_count,
        chunk_count=record.chunk_count,
        reused=submission.reused,
    )


def run_reference_benchmark(
    suite: ReferenceSuite,
    samples_root: str | Path,
    *,
    top_k: int = 5,
    embedding_model: str | None = None,
    included_statuses: Iterable[str] = DEFAULT_INCLUDED_STATUSES,
    download_missing: bool = False,
) -> ReferenceBenchmarkReport:
    statuses = frozenset(included_statuses)
    invalid_statuses = statuses - DEFAULT_INCLUDED_STATUSES
    if invalid_statuses:
        raise ValueError(
            "Status nao executaveis: " + ", ".join(sorted(invalid_statuses))
        )
    embedding = embedding_model or embedding_provider_from_environment()
    process_results: list[ReferenceProcessBenchmark] = []

    for process in suite.processes:
        selected_cases = [
            case for case in process.cases if case.review_status in statuses
        ]
        if not selected_cases:
            continue
        prepared = prepare_reference_process(
            process,
            samples_root,
            download_missing=download_missing,
        )
        routing = run_routing_benchmark(
            processo_id=prepared.processo_id,
            cases=[
                EvaluationCase(
                    id=case.id,
                    pergunta=case.pergunta,
                    expected_pages=case.expected_pages,
                    expected_terms=case.expected_terms,
                )
                for case in selected_cases
            ],
            top_k=top_k,
            embedding_model=embedding,
            llm_cases=0,
        )
        process_results.append(
            ReferenceProcessBenchmark(
                reference_id=prepared.reference_id,
                domain=prepared.domain,
                processo_id=prepared.processo_id,
                document=prepared.document,
                page_count=prepared.page_count,
                chunk_count=prepared.chunk_count,
                reused=prepared.reused,
                review_status_counts=_status_counts(selected_cases),
                routing=routing,
            )
        )

    return _build_report(suite.id, embedding, top_k, process_results)


def write_reference_benchmark_report(
    report: ReferenceBenchmarkReport,
    output_path: str | Path,
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    path.with_suffix(".md").write_text(
        render_reference_benchmark_markdown(report),
        encoding="utf-8",
    )


def render_reference_benchmark_markdown(report: ReferenceBenchmarkReport) -> str:
    lines = [
        "# Benchmark multidominio de referencia",
        "",
        f"Suite: `{report.suite_id}`",
        "",
        f"Recuperador: `{report.embedding_model}`",
        "",
        f"Processos: `{report.total_processes}`",
        "",
        f"Casos: `{report.total_cases}`",
        "",
        "## Resultado agregado",
        "",
        "| Metrica | Pergunta bruta | Triagem com fusao |",
        "|---|---:|---:|",
        f"| Hit rate | {report.raw_hit_rate:.4f} | {report.routed_hit_rate:.4f} |",
        f"| MRR | {report.raw_mrr:.4f} | {report.routed_mrr:.4f} |",
        "",
        f"Melhoraram: `{report.improved_cases}`",
        "",
        f"Pioraram: `{report.degraded_cases}`",
        "",
        f"Empataram: `{report.tied_cases}`",
        "",
        "## Resultado por processo",
        "",
        "| Processo | Dominio | Casos | Hit bruto | Hit triagem | MRR bruto | MRR triagem |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for result in report.processes:
        routing = result.routing
        lines.append(
            f"| `{result.reference_id}` | `{result.domain}` | "
            f"{routing.total_cases} | {routing.raw_hit_rate:.4f} | "
            f"{routing.routed_hit_rate:.4f} | {routing.raw_mrr:.4f} | "
            f"{routing.routed_mrr:.4f} |"
        )
    lines.extend(
        [
            "",
            "## Estado da revisao",
            "",
            *[
                f"{status}: `{count}`"
                for status, count in sorted(report.review_status_counts.items())
            ],
        ]
    )
    return "\n".join(lines) + "\n"


def _build_report(
    suite_id: str,
    embedding_model: str,
    top_k: int,
    process_results: list[ReferenceProcessBenchmark],
) -> ReferenceBenchmarkReport:
    total_cases = sum(result.routing.total_cases for result in process_results)
    return ReferenceBenchmarkReport(
        suite_id=suite_id,
        embedding_model=embedding_model,
        top_k=top_k,
        total_processes=len(process_results),
        total_cases=total_cases,
        review_status_counts=_merge_status_counts(process_results),
        raw_hit_rate=_weighted_metric(process_results, "raw_hit_rate"),
        routed_hit_rate=_weighted_metric(process_results, "routed_hit_rate"),
        raw_mrr=_weighted_metric(process_results, "raw_mrr"),
        routed_mrr=_weighted_metric(process_results, "routed_mrr"),
        improved_cases=sum(
            result.routing.improved_cases for result in process_results
        ),
        degraded_cases=sum(
            result.routing.degraded_cases for result in process_results
        ),
        tied_cases=sum(result.routing.tied_cases for result in process_results),
        processes=process_results,
    )


def _weighted_metric(
    results: list[ReferenceProcessBenchmark],
    field_name: str,
) -> float:
    values = [
        getattr(result.routing, field_name)
        for result in results
        for _ in range(result.routing.total_cases)
    ]
    return round(mean(values), 4) if values else 0.0


def _status_counts(cases: Iterable[ReferenceCase]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in cases:
        status = case.review_status
        counts[status] = counts.get(status, 0) + 1
    return counts


def _merge_status_counts(
    results: list[ReferenceProcessBenchmark],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        for status, count in result.review_status_counts.items():
            counts[status] = counts.get(status, 0) + count
    return counts


def _load_process_record(processo_id: str) -> ProcessoRecord:
    connection = connect_database()
    initialize_database(connection)
    try:
        record = ProcessoRepository(connection).get(processo_id)
    finally:
        connection.close()
    if record is None:
        raise RuntimeError(f"Processo ingerido nao encontrado: {processo_id}")
    return record


def _download_bytes(url: str) -> bytes:
    response = httpx.get(url, follow_redirects=True, timeout=60.0)
    response.raise_for_status()
    return response.content
