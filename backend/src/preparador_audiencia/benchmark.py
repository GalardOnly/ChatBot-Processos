from __future__ import annotations

import csv
import json
import re
import time
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from preparador_audiencia.embeddings import embedding_provider_from_spec
from preparador_audiencia.ensemble import is_ensemble_spec, parse_ensemble_spec
from preparador_audiencia.pdf_extraction import PdfExtractionReport, extract_pdf_report
from preparador_audiencia.repositories import ChunkRecord
from preparador_audiencia.vector_store import ChromaVectorStore, safe_collection_name

JURISTCU_BASE_URL = "https://huggingface.co/datasets/LeandroRibeiro/JurisTCU/resolve/main"
JURISTCU_FILES = ("doc.csv", "query.csv", "qrel.csv")


@dataclass(frozen=True)
class BenchmarkSource:
    id: str
    title: str
    kind: str
    url: str
    origin: str
    license: str | None = None
    download_url: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class DownloadedBenchmarkFile:
    source_id: str
    path: str | None
    bytes_written: int
    skipped: bool
    message: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class JurisTCUDocument:
    doc_id: str
    text: str


@dataclass(frozen=True)
class JurisTCUQuery:
    query_id: str
    text: str


@dataclass(frozen=True)
class JurisTCUCaseResult:
    query_id: str
    query: str
    expected_doc_ids: list[str]
    top_doc_ids: list[str]
    hit: bool
    reciprocal_rank: float
    precision_at_k: float


@dataclass(frozen=True)
class JurisTCUBenchmarkReport:
    dataset: str
    embedding_model: str
    indexed_documents: int
    reused_indexes: list[str]
    rebuilt_indexes: list[str]
    query_count: int
    top_k: int
    hit_rate: float
    mean_reciprocal_rank: float
    mean_precision_at_k: float
    cases: list[JurisTCUCaseResult]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PdfBenchmarkFileResult:
    file_name: str
    path: str
    page_count: int
    processed_pages: int
    total_char_count: int
    empty_page_count: int
    low_text_page_count: int
    image_page_count: int
    ocr_page_count: int
    extraction_methods: dict[str, int]
    elapsed_ms: int
    error: str | None = None


@dataclass(frozen=True)
class PdfBenchmarkReport:
    family: str
    ocr_enabled: bool
    max_pages: int | None
    files: list[PdfBenchmarkFileResult]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def load_benchmark_sources(path: str | Path) -> list[BenchmarkSource]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    items = payload["sources"] if isinstance(payload, dict) else payload
    return [
        BenchmarkSource(
            id=str(item["id"]),
            title=str(item["title"]),
            kind=str(item["kind"]),
            url=str(item["url"]),
            origin=str(item["origin"]),
            license=item.get("license"),
            download_url=item.get("download_url"),
            notes=item.get("notes"),
        )
        for item in items
    ]


def sources_by_kind(sources: list[BenchmarkSource], kind: str | None) -> list[BenchmarkSource]:
    if kind is None:
        return sources
    return [source for source in sources if source.kind == kind]


def download_pdf_sources(
    sources: list[BenchmarkSource],
    output_dir: str | Path,
) -> list[DownloadedBenchmarkFile]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    return [download_pdf_source(source, output) for source in sources]


def download_pdf_source(
    source: BenchmarkSource,
    output_dir: str | Path,
    fetcher: Callable[[str], bytes] | None = None,
) -> DownloadedBenchmarkFile:
    if source.kind != "pdf":
        return DownloadedBenchmarkFile(
            source_id=source.id,
            path=None,
            bytes_written=0,
            skipped=True,
            message="fonte nao e PDF",
        )

    url = source.download_url or source.url
    filename = _safe_filename_from_url(url, fallback=f"{source.id}.pdf")
    path = Path(output_dir) / filename
    data = (fetcher or _download_bytes)(url)

    if not data.startswith(b"%PDF"):
        return DownloadedBenchmarkFile(
            source_id=source.id,
            path=None,
            bytes_written=0,
            skipped=True,
            message="conteudo baixado nao parece ser PDF",
        )

    path.write_bytes(data)
    return DownloadedBenchmarkFile(
        source_id=source.id,
        path=str(path),
        bytes_written=len(data),
        skipped=False,
        message="baixado",
    )


def render_sources_table(sources: list[BenchmarkSource]) -> str:
    lines = ["ID | Tipo | Origem | Titulo"]
    for source in sources:
        lines.append(f"{source.id} | {source.kind} | {source.origin} | {source.title}")
    return "\n".join(lines)


def run_pdf_benchmark(
    paths: list[str | Path],
    *,
    family: str = "pdfs-publicos",
    ocr_enabled: bool = True,
    max_pages: int | None = None,
) -> PdfBenchmarkReport:
    return PdfBenchmarkReport(
        family=family,
        ocr_enabled=ocr_enabled,
        max_pages=max_pages,
        files=[
            _run_pdf_file_benchmark(path, ocr_enabled=ocr_enabled, max_pages=max_pages)
            for path in paths
        ],
    )


def write_pdf_benchmark_report(report: PdfBenchmarkReport, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    path.with_suffix(".md").write_text(render_pdf_benchmark_markdown(report), encoding="utf-8")


def render_pdf_benchmark_markdown(report: PdfBenchmarkReport) -> str:
    page_limit = report.max_pages if report.max_pages is not None else "sem limite"
    lines = [
        "# Benchmark de PDFs",
        "",
        f"Familia: `{report.family}`",
        f"OCR ativo: `{report.ocr_enabled}`",
        f"Limite de paginas: `{page_limit}`",
        "",
    ]
    for file_result in report.files:
        page_summary = f"`{file_result.processed_pages}` de `{file_result.page_count}`"
        lines.extend(
            [
                f"Arquivo: `{file_result.file_name}`",
                f"Paginas processadas: {page_summary}",
                f"Caracteres extraidos: `{file_result.total_char_count}`",
                f"Paginas com imagem: `{file_result.image_page_count}`",
                f"Paginas com OCR: `{file_result.ocr_page_count}`",
                f"Paginas vazias: `{file_result.empty_page_count}`",
                f"Paginas com pouco texto: `{file_result.low_text_page_count}`",
                f"Metodos: `{file_result.extraction_methods}`",
                f"Tempo: `{file_result.elapsed_ms} ms`",
                f"Erro: `{file_result.error or ''}`",
                "",
            ]
        )
    return "\n".join(lines)


def _run_pdf_file_benchmark(
    path: str | Path,
    *,
    ocr_enabled: bool,
    max_pages: int | None,
) -> PdfBenchmarkFileResult:
    started = time.perf_counter()
    pdf_path = Path(path)
    try:
        report = extract_pdf_report(
            pdf_path,
            ocr_enabled=ocr_enabled,
            max_pages=max_pages,
        )
        return _pdf_file_result(pdf_path, report, _elapsed_ms(started))
    except Exception as exc:
        return PdfBenchmarkFileResult(
            file_name=pdf_path.name,
            path=str(pdf_path),
            page_count=0,
            processed_pages=0,
            total_char_count=0,
            empty_page_count=0,
            low_text_page_count=0,
            image_page_count=0,
            ocr_page_count=0,
            extraction_methods={},
            elapsed_ms=_elapsed_ms(started),
            error=str(exc),
        )


def ensure_juristcu_files(cache_dir: str | Path) -> dict[str, Path]:
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    paths = {name: cache / name for name in JURISTCU_FILES}
    for name, path in paths.items():
        if not path.exists():
            path.write_bytes(_download_bytes(f"{JURISTCU_BASE_URL}/{name}"))
    return paths


def _pdf_file_result(
    path: Path,
    report: PdfExtractionReport,
    elapsed_ms: int,
) -> PdfBenchmarkFileResult:
    methods: dict[str, int] = {}
    for page in report.pages:
        methods[page.extraction_method] = methods.get(page.extraction_method, 0) + 1
    return PdfBenchmarkFileResult(
        file_name=report.file_name,
        path=str(path),
        page_count=report.page_count,
        processed_pages=len(report.pages),
        total_char_count=report.total_char_count,
        empty_page_count=report.empty_page_count,
        low_text_page_count=report.low_text_page_count,
        image_page_count=sum(1 for page in report.pages if page.image_count > 0),
        ocr_page_count=sum(1 for page in report.pages if page.ocr_applied),
        extraction_methods=methods,
        elapsed_ms=elapsed_ms,
    )


def run_juristcu_benchmark(
    cache_dir: str | Path,
    *,
    query_limit: int = 5,
    distractor_limit: int = 250,
    embedding_model: str = "hash",
    top_k: int = 10,
    reindex: bool = False,
) -> JurisTCUBenchmarkReport:
    paths = ensure_juristcu_files(cache_dir)
    queries = _load_juristcu_queries(paths["query.csv"], query_limit)
    qrels = _load_juristcu_qrels(paths["qrel.csv"], {query.query_id for query in queries})
    expected_doc_ids = {
        doc_id
        for doc_scores in qrels.values()
        for doc_id, score in doc_scores.items()
        if score > 0
    }
    documents = _load_juristcu_documents(paths["doc.csv"], expected_doc_ids, distractor_limit)
    processo_id = f"juristcu_{query_limit}_{distractor_limit}"
    chunks = _documents_to_chunks(processo_id, documents)
    retrievers = _index_juristcu_retrievers(
        processo_id=processo_id,
        chunks=chunks,
        embedding_model=embedding_model,
        reindex=reindex,
    )

    case_results = []
    for query in queries:
        top_doc_ids = _search_juristcu_retrievers(
            processo_id=processo_id,
            query=query.text,
            retrievers=retrievers,
            top_k=top_k,
        )
        relevant = [
            doc_id
            for doc_id, score in qrels.get(query.query_id, {}).items()
            if score > 0
        ]
        case_results.append(
            JurisTCUCaseResult(
                query_id=query.query_id,
                query=query.text,
                expected_doc_ids=relevant,
                top_doc_ids=top_doc_ids,
                hit=any(doc_id in set(relevant) for doc_id in top_doc_ids),
                reciprocal_rank=_doc_reciprocal_rank(top_doc_ids, relevant),
                precision_at_k=_precision_at_k(top_doc_ids, relevant),
            )
        )

    return JurisTCUBenchmarkReport(
        dataset="LeandroRibeiro/JurisTCU",
        embedding_model=embedding_model,
        indexed_documents=len(documents),
        reused_indexes=[retriever.spec for retriever in retrievers if retriever.reused_index],
        rebuilt_indexes=[retriever.spec for retriever in retrievers if not retriever.reused_index],
        query_count=len(queries),
        top_k=top_k,
        hit_rate=_average([1.0 if case.hit else 0.0 for case in case_results]),
        mean_reciprocal_rank=_average([case.reciprocal_rank for case in case_results]),
        mean_precision_at_k=_average([case.precision_at_k for case in case_results]),
        cases=case_results,
    )


@dataclass(frozen=True)
class JurisTCURetriever:
    spec: str
    provider: object
    store: ChromaVectorStore
    reused_index: bool


def _index_juristcu_retrievers(
    processo_id: str,
    chunks: list[ChunkRecord],
    embedding_model: str,
    reindex: bool,
) -> list[JurisTCURetriever]:
    specs = (
        parse_ensemble_spec(embedding_model)
        if is_ensemble_spec(embedding_model)
        else [embedding_model]
    )
    retrievers = []
    for spec in specs:
        collection_name = safe_collection_name("juristcu", spec)
        store = ChromaVectorStore(collection_name=collection_name)
        reused = not reindex and store.count_process_chunks(processo_id) == len(chunks)
        provider = embedding_provider_from_spec(spec)
        if not reused:
            embeddings = provider.embed_texts([chunk.text for chunk in chunks])
            store.replace_process_chunks(processo_id, chunks, embeddings)
        retrievers.append(
            JurisTCURetriever(
                spec=spec,
                provider=provider,
                store=store,
                reused_index=reused,
            )
        )
    return retrievers


def _search_juristcu_retrievers(
    processo_id: str,
    query: str,
    retrievers: list[JurisTCURetriever],
    top_k: int,
) -> list[str]:
    if len(retrievers) == 1:
        retriever = retrievers[0]
        query_embedding = retriever.provider.embed_query(query)
        hits = retriever.store.search(
            processo_id=processo_id,
            query_embedding=query_embedding,
            top_k=top_k,
        )
        return [str(hit.document_type) for hit in hits if hit.document_type]

    combined: dict[str, dict[str, float | int]] = {}
    per_model_top_k = max(top_k * 2, 10)
    for retriever in retrievers:
        query_embedding = retriever.provider.embed_query(query)
        hits = retriever.store.search(
            processo_id=processo_id,
            query_embedding=query_embedding,
            top_k=per_model_top_k,
        )
        for rank, hit in enumerate(hits, start=1):
            if not hit.document_type:
                continue
            doc_id = str(hit.document_type)
            stats = combined.setdefault(
                doc_id,
                {"votes": 0, "score_sum": 0.0, "best_rank_score": 0.0},
            )
            rank_score = 1.0 / rank
            score = (0.5 * hit.score) + (0.5 * rank_score)
            stats["votes"] = int(stats["votes"]) + 1
            stats["score_sum"] = float(stats["score_sum"]) + score
            stats["best_rank_score"] = max(float(stats["best_rank_score"]), rank_score)

    ranked = sorted(
        combined.items(),
        key=lambda item: (
            int(item[1]["votes"]),
            float(item[1]["score_sum"]),
            float(item[1]["best_rank_score"]),
        ),
        reverse=True,
    )
    return [doc_id for doc_id, _ in ranked[:top_k]]


def write_juristcu_report(report: JurisTCUBenchmarkReport, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    path.with_suffix(".md").write_text(render_juristcu_markdown(report), encoding="utf-8")


def render_juristcu_markdown(report: JurisTCUBenchmarkReport) -> str:
    lines = [
        "# Benchmark JurisTCU",
        "",
        f"Dataset: `{report.dataset}`",
        f"Embedding: `{report.embedding_model}`",
        f"Documentos indexados: `{report.indexed_documents}`",
        f"Indices reaproveitados: `{', '.join(report.reused_indexes) or 'nenhum'}`",
        f"Indices recriados: `{', '.join(report.rebuilt_indexes) or 'nenhum'}`",
        f"Consultas avaliadas: `{report.query_count}`",
        f"Top K: `{report.top_k}`",
        f"Hit rate: `{report.hit_rate:.4f}`",
        f"MRR: `{report.mean_reciprocal_rank:.4f}`",
        f"Precisao media no Top K: `{report.mean_precision_at_k:.4f}`",
        "",
        "Resultados por consulta:",
        "",
    ]
    for case in report.cases:
        lines.extend(
            [
                f"Consulta {case.query_id}: {case.query}",
                f"Esperados: {', '.join(case.expected_doc_ids[:5]) or 'nenhum'}",
                f"Retornados: {', '.join(case.top_doc_ids[:5]) or 'nenhum'}",
                (
                    f"Hit: {case.hit} | MRR: {case.reciprocal_rank:.4f} | "
                    f"Precisao: {case.precision_at_k:.4f}"
                ),
                "",
            ]
        )
    return "\n".join(lines)


def _download_bytes(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "preparador-audiencia-benchmark/0.1"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _load_juristcu_queries(path: Path, limit: int) -> list[JurisTCUQuery]:
    queries = []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            queries.append(JurisTCUQuery(query_id=str(row["ID"]), text=str(row["TEXT"])))
            if len(queries) >= limit:
                break
    return queries


def _load_juristcu_qrels(path: Path, query_ids: set[str]) -> dict[str, dict[str, int]]:
    qrels: dict[str, dict[str, int]] = {query_id: {} for query_id in query_ids}
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            query_id = str(row["QUERY_ID"])
            if query_id in qrels:
                qrels[query_id][str(row["DOC_ID"])] = int(float(row["SCORE"]))
    return qrels


def _load_juristcu_documents(
    path: Path,
    required_doc_ids: set[str],
    distractor_limit: int,
) -> list[JurisTCUDocument]:
    documents_by_id: dict[str, JurisTCUDocument] = {}
    distractors = 0
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            doc_id = str(row["KEY"])
            is_required = doc_id in required_doc_ids
            if not is_required and distractors >= distractor_limit:
                continue
            documents_by_id[doc_id] = JurisTCUDocument(doc_id=doc_id, text=_juristcu_text(row))
            if not is_required:
                distractors += 1
            if required_doc_ids.issubset(documents_by_id) and distractors >= distractor_limit:
                break
    return list(documents_by_id.values())


def _juristcu_text(row: dict[str, str]) -> str:
    fields = [
        "AREA",
        "TEMA",
        "SUBTEMA",
        "ENUNCIADO",
        "EXCERTO",
        "INDEXADORESCONSOLIDADOS",
        "REFERENCIALEGAL",
    ]
    text = "\n".join(str(row.get(field) or "") for field in fields)
    return re.sub(r"<[^>]+>", " ", text)


def _documents_to_chunks(processo_id: str, documents: list[JurisTCUDocument]) -> list[ChunkRecord]:
    return [
        ChunkRecord(
            id=index,
            processo_id=processo_id,
            page_number=index,
            chunk_index=0,
            text=document.text,
            document_type=document.doc_id,
            source_confidence="alta",
            vector_id=None,
            created_at="",
        )
        for index, document in enumerate(documents, start=1)
    ]


def _doc_reciprocal_rank(top_doc_ids: list[str], expected_doc_ids: list[str]) -> float:
    expected = set(expected_doc_ids)
    for index, doc_id in enumerate(top_doc_ids, start=1):
        if doc_id in expected:
            return round(1.0 / index, 4)
    return 0.0


def _precision_at_k(top_doc_ids: list[str], expected_doc_ids: list[str]) -> float:
    if not top_doc_ids:
        return 0.0
    expected = set(expected_doc_ids)
    return round(sum(1 for doc_id in top_doc_ids if doc_id in expected) / len(top_doc_ids), 4)


def _average(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _safe_filename_from_url(url: str, fallback: str) -> str:
    path = unquote(urlparse(url).path)
    name = Path(path).name or fallback
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    if not name.lower().endswith(".pdf"):
        name = f"{name or fallback}.pdf"
    return name
