from preparador_audiencia.chunking import TextChunk
from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.embeddings import HashEmbeddingProvider
from preparador_audiencia.repositories import ChunkRepository, ProcessoRepository
from preparador_audiencia.search import index_process_chunks, search_process
from preparador_audiencia.vector_store import ChromaVectorStore


def test_index_and_search_returns_relevant_page(tmp_path) -> None:
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
            TextChunk(
                page_number=1,
                chunk_index=0,
                text="Peticao inicial com relato dos fatos.",
                document_type=None,
            ),
            TextChunk(
                page_number=2,
                chunk_index=0,
                text="Designada audiencia de instrucao para 20/08/2026.",
                document_type="audiencia",
            ),
        ],
    )

    provider = HashEmbeddingProvider(dimensions=64)
    store = ChromaVectorStore(path=tmp_path / "chroma")
    indexed = index_process_chunks("proc_123", chunks, provider, store)
    results = search_process("proc_123", "qual a data da audiencia?", 2, provider, store)

    assert indexed == 2
    assert results[0].page_number == 2
    assert results[0].chunk_index == 0
    assert results[0].document_type == "audiencia"
    assert chunks.list_for_processo("proc_123")[1].vector_id is not None


def test_index_process_chunks_uses_small_batches_and_reports_progress(tmp_path) -> None:
    connection = connect_database(tmp_path / "test.sqlite3")
    initialize_database(connection)
    ProcessoRepository(connection).create_pending(
        processo_id="proc_batch",
        filename="processo.pdf",
        file_path="storage/processo.pdf",
        sha256_digest="batch",
    )
    chunks = ChunkRepository(connection)
    chunks.replace_for_processo(
        "proc_batch",
        [
            TextChunk(page_number=1, chunk_index=index, text=f"Trecho {index}")
            for index in range(5)
        ],
    )
    provider = HashEmbeddingProvider(dimensions=16)
    store = ChromaVectorStore(path=tmp_path / "chroma")
    progress = []

    indexed = index_process_chunks(
        "proc_batch",
        chunks,
        provider,
        store,
        batch_size=2,
        progress_callback=lambda current, total: progress.append((current, total)),
    )

    assert indexed == 5
    assert progress == [(2, 5), (4, 5), (5, 5)]
