from preparador_audiencia.chunking import TextChunk
from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.nullity_analysis_repository import (
    NullityAnalysisRepository,
)
from preparador_audiencia.repositories import ChunkRepository, ProcessoRepository


def _create_process(connection) -> None:
    ProcessoRepository(connection).create_pending(
        "proc-1",
        "processo.pdf",
        "storage/processo.pdf",
        "abc",
    )
    ChunkRepository(connection).replace_for_processo(
        "proc-1",
        [TextChunk(page_number=1, chunk_index=0, text="Busca pessoal.")],
    )


def test_repository_saves_updates_and_lists_by_topic(tmp_path) -> None:
    connection = connect_database(tmp_path / "test.sqlite3")
    initialize_database(connection)
    _create_process(connection)
    repository = NullityAnalysisRepository(connection)

    first = repository.save(
        "proc-1",
        "cadeia_custodia",
        catalog_version="2026.08.04",
        conclusion="inconclusiva",
        payload={"resumo": "Primeira analise."},
        model="sistema",
        fallback_used=False,
        search_mode="lexical",
    )
    updated = repository.save(
        "proc-1",
        "cadeia_custodia",
        catalog_version="2026.08.04",
        conclusion="indicios_suficientes",
        payload={"resumo": "Analise atualizada."},
        model="gemini:test",
        fallback_used=False,
        search_mode="hibrida",
    )

    assert first.created_at == updated.created_at
    assert updated.conclusion == "indicios_suficientes"
    assert updated.payload["resumo"] == "Analise atualizada."
    assert repository.list_for_process("proc-1") == [updated]
    connection.close()


def test_replacing_chunks_invalidates_saved_nullity_analyses(tmp_path) -> None:
    connection = connect_database(tmp_path / "test.sqlite3")
    initialize_database(connection)
    _create_process(connection)
    repository = NullityAnalysisRepository(connection)
    repository.save(
        "proc-1",
        "busca_pessoal_domiciliar",
        catalog_version="2026.08.04",
        conclusion="inconclusiva",
        payload={"resumo": "Analise."},
        model="sistema",
        fallback_used=False,
        search_mode="lexical",
    )

    ChunkRepository(connection).replace_for_processo(
        "proc-1",
        [TextChunk(page_number=2, chunk_index=0, text="Texto reprocessado.")],
    )

    assert repository.list_for_process("proc-1") == []
    connection.close()
