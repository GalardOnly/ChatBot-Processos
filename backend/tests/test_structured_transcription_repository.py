from preparador_audiencia.chunking import TextChunk
from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.repositories import ChunkRepository, ProcessoRepository
from preparador_audiencia.structured_transcription_repository import (
    StructuredTranscriptionRepository,
)


def _repositories(tmp_path):
    connection = connect_database(tmp_path / "test.sqlite3")
    initialize_database(connection)
    ProcessoRepository(connection).create_pending(
        "proc_1",
        "processo.pdf",
        "storage/processo.pdf",
        "abc",
    )
    return connection, StructuredTranscriptionRepository(connection)


def test_repository_persists_structured_payload(tmp_path) -> None:
    connection, repository = _repositories(tmp_path)

    saved = repository.save(
        "proc_1",
        status="concluido",
        payload={"depoimentos": [{"ordem": 1}], "avisos": []},
    )
    loaded = repository.get("proc_1")

    assert loaded == saved
    assert loaded is not None
    assert loaded.schema_version == "2.0"
    assert loaded.payload["depoimentos"] == [{"ordem": 1}]
    connection.close()


def test_replacing_chunks_invalidates_cached_transcription(tmp_path) -> None:
    connection, repository = _repositories(tmp_path)
    repository.save(
        "proc_1",
        status="sem_depoimentos",
        payload={"depoimentos": [], "avisos": []},
    )

    ChunkRepository(connection).replace_for_processo(
        "proc_1",
        [TextChunk(page_number=1, chunk_index=0, text="novo texto")],
    )

    assert repository.get("proc_1") is None
    connection.close()
