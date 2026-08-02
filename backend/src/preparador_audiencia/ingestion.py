from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import BoundedSemaphore
from uuid import uuid4

from preparador_audiencia.chunking import chunk_extracted_pages
from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.pdf_extraction import extract_pdf_report
from preparador_audiencia.repositories import ChunkRepository, ProcessoRepository
from preparador_audiencia.retrieval import index_process_chunks_configured
from preparador_audiencia.settings import (
    ocr_workers_from_environment,
    ocr_zoom_from_environment,
    storage_dir_from_environment,
)

_PROCESSING_SEMAPHORE = BoundedSemaphore(1)


@dataclass(frozen=True)
class ProcessSubmission:
    processo_id: str
    status: str
    reused: bool
    should_process: bool


def create_processo_from_pdf(
    filename: str,
    content: bytes,
    storage_dir: Path | None = None,
) -> ProcessSubmission:
    resolved_storage_dir = storage_dir or storage_dir_from_environment()
    resolved_storage_dir.mkdir(parents=True, exist_ok=True)

    digest = sha256(content).hexdigest()
    connection = connect_database()
    initialize_database(connection)
    processos = ProcessoRepository(connection)
    reusable = processos.find_reusable_by_sha256(digest)
    if reusable is not None and Path(reusable.file_path).is_file():
        return ProcessSubmission(
            processo_id=reusable.id,
            status=reusable.status,
            reused=True,
            should_process=False,
        )

    processo_id = f"proc_{uuid4().hex[:12]}"
    safe_filename = _safe_filename(filename or "processo.pdf")
    file_path = resolved_storage_dir / f"{processo_id}-{safe_filename}"
    file_path.write_bytes(content)

    processos.create_pending(
        processo_id=processo_id,
        filename=safe_filename,
        file_path=str(file_path),
        sha256_digest=digest,
    )
    return ProcessSubmission(
        processo_id=processo_id,
        status="pendente",
        reused=False,
        should_process=True,
    )


def create_processo_from_staged_pdf(
    filename: str,
    staged_path: Path,
    sha256_digest: str,
    storage_dir: Path | None = None,
) -> ProcessSubmission:
    resolved_storage_dir = storage_dir or storage_dir_from_environment()
    resolved_storage_dir.mkdir(parents=True, exist_ok=True)

    connection = connect_database()
    initialize_database(connection)
    processos = ProcessoRepository(connection)
    reusable = processos.find_reusable_by_sha256(sha256_digest)
    if reusable is not None and Path(reusable.file_path).is_file():
        staged_path.unlink(missing_ok=True)
        return ProcessSubmission(
            processo_id=reusable.id,
            status=reusable.status,
            reused=True,
            should_process=False,
        )

    processo_id = f"proc_{uuid4().hex[:12]}"
    safe_filename = _safe_filename(filename or "processo.pdf")
    file_path = resolved_storage_dir / f"{processo_id}-{safe_filename}"
    staged_path.replace(file_path)

    processos.create_pending(
        processo_id=processo_id,
        filename=safe_filename,
        file_path=str(file_path),
        sha256_digest=sha256_digest,
    )
    return ProcessSubmission(
        processo_id=processo_id,
        status="pendente",
        reused=False,
        should_process=True,
    )


def process_pdf(processo_id: str) -> None:
    with _PROCESSING_SEMAPHORE:
        _process_pdf_exclusively(processo_id)


def _process_pdf_exclusively(processo_id: str) -> None:
    connection = connect_database()
    initialize_database(connection)
    processos = ProcessoRepository(connection)
    chunks = ChunkRepository(connection)
    processo = processos.get(processo_id)
    if processo is None:
        raise ValueError(f"Processo nao encontrado: {processo_id}")
    if processo.status == "concluido":
        return

    try:
        processos.mark_processing(processo_id)
        report = extract_pdf_report(
            processo.file_path,
            ocr_zoom=ocr_zoom_from_environment(),
            ocr_workers=ocr_workers_from_environment(),
            progress_callback=lambda current, total: _report_extraction_progress(
                processos,
                processo_id,
                current,
                total,
            ),
        )
        processos.update_progress(
            processo_id,
            stage="criando_chunks",
            current=0,
            total=max(1, report.page_count),
            message="Organizando o texto por pagina",
            page_count=report.page_count,
        )
        extracted_chunks = chunk_extracted_pages(report.pages)
        chunks.replace_for_processo(processo_id, extracted_chunks)
        processos.update_progress(
            processo_id,
            stage="indexando",
            current=0,
            total=max(1, len(extracted_chunks)),
            message="Preparando o indice juridico",
            chunk_count=len(extracted_chunks),
        )
        index_process_chunks_configured(
            processo_id,
            chunks,
            progress_callback=lambda spec, model_index, model_count, current, total: (
                _report_index_progress(
                    processos,
                    processo_id,
                    spec,
                    model_index,
                    model_count,
                    current,
                    total,
                )
            ),
        )
        processos.mark_completed(
            processo_id,
            page_count=report.page_count,
            chunk_count=len(extracted_chunks),
        )
    except Exception as exc:
        processos.mark_error(processo_id, str(exc))
        raise


def _report_extraction_progress(
    processos: ProcessoRepository,
    processo_id: str,
    current: int,
    total: int,
) -> None:
    if current not in {1, total} and current % 2:
        return
    processos.update_progress(
        processo_id,
        stage="extraindo",
        current=current,
        total=total,
        message=f"Extraindo texto e OCR: pagina {current} de {total}",
        page_count=current,
    )


def _report_index_progress(
    processos: ProcessoRepository,
    processo_id: str,
    spec: str,
    model_index: int,
    model_count: int,
    current: int,
    total: int,
) -> None:
    safe_total = max(1, total)
    overall_total = safe_total * model_count
    overall_current = (model_index - 1) * safe_total + current
    processos.update_progress(
        processo_id,
        stage="indexando",
        current=overall_current,
        total=overall_total,
        message=(
            f"Gerando indice juridico {model_index} de {model_count} "
            f"({spec}): {current} de {total} trechos"
        ),
    )


def _safe_filename(filename: str) -> str:
    cleaned = Path(filename).name.strip().replace("\\", "-").replace("/", "-")
    return cleaned or "processo.pdf"
