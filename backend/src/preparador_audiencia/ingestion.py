from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from preparador_audiencia.chunking import chunk_extracted_pages
from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.pdf_extraction import extract_pdf_report
from preparador_audiencia.repositories import ChunkRepository, ProcessoRepository
from preparador_audiencia.retrieval import index_process_chunks_configured
from preparador_audiencia.settings import storage_dir_from_environment


def create_processo_from_pdf(
    filename: str,
    content: bytes,
    storage_dir: Path | None = None,
) -> str:
    resolved_storage_dir = storage_dir or storage_dir_from_environment()
    resolved_storage_dir.mkdir(parents=True, exist_ok=True)

    processo_id = f"proc_{uuid4().hex[:12]}"
    safe_filename = _safe_filename(filename or "processo.pdf")
    file_path = resolved_storage_dir / f"{processo_id}-{safe_filename}"
    file_path.write_bytes(content)

    connection = connect_database()
    initialize_database(connection)
    ProcessoRepository(connection).create_pending(
        processo_id=processo_id,
        filename=safe_filename,
        file_path=str(file_path),
        sha256_digest=sha256(content).hexdigest(),
    )
    return processo_id


def process_pdf(processo_id: str) -> None:
    connection = connect_database()
    initialize_database(connection)
    processos = ProcessoRepository(connection)
    chunks = ChunkRepository(connection)
    processo = processos.get(processo_id)
    if processo is None:
        raise ValueError(f"Processo nao encontrado: {processo_id}")

    try:
        processos.mark_processing(processo_id)
        report = extract_pdf_report(processo.file_path)
        extracted_chunks = chunk_extracted_pages(report.pages)
        chunks.replace_for_processo(processo_id, extracted_chunks)
        index_process_chunks_configured(processo_id, chunks)
        processos.mark_completed(
            processo_id,
            page_count=report.page_count,
            chunk_count=len(extracted_chunks),
        )
    except Exception as exc:
        processos.mark_error(processo_id, str(exc))
        raise


def _safe_filename(filename: str) -> str:
    cleaned = Path(filename).name.strip().replace("\\", "-").replace("/", "-")
    return cleaned or "processo.pdf"
