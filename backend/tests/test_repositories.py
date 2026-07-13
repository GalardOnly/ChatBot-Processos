from preparador_audiencia.chunking import TextChunk
from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.repositories import ChunkRepository, ProcessoRepository


def test_process_repository_lifecycle(tmp_path) -> None:
    connection = connect_database(tmp_path / "test.sqlite3")
    initialize_database(connection)
    processos = ProcessoRepository(connection)

    created = processos.create_pending(
        processo_id="proc_123",
        filename="processo.pdf",
        file_path="storage/processo.pdf",
        sha256_digest="abc",
    )
    assert created.status == "pendente"

    processos.mark_processing("proc_123")
    assert processos.get("proc_123").status == "processando"

    processos.mark_completed("proc_123", page_count=2, chunk_count=5)
    completed = processos.get("proc_123")
    assert completed.status == "concluido"
    assert completed.page_count == 2
    assert completed.chunk_count == 5


def test_chunk_repository_replaces_chunks(tmp_path) -> None:
    connection = connect_database(tmp_path / "test.sqlite3")
    initialize_database(connection)
    ProcessoRepository(connection).create_pending(
        processo_id="proc_123",
        filename="processo.pdf",
        file_path="storage/processo.pdf",
        sha256_digest="abc",
    )
    chunks = ChunkRepository(connection)

    chunks.replace_for_processo(
        "proc_123",
        [
            TextChunk(page_number=1, chunk_index=0, text="A", document_type=None),
            TextChunk(page_number=1, chunk_index=1, text="B", document_type="edital"),
        ],
    )
    assert chunks.count_for_processo("proc_123") == 2

    chunks.replace_for_processo(
        "proc_123",
        [TextChunk(page_number=2, chunk_index=0, text="C", document_type=None)],
    )
    assert chunks.count_for_processo("proc_123") == 1

