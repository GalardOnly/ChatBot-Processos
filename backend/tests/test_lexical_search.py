from preparador_audiencia.chunking import TextChunk
from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.lexical_index import process_fts_table_name
from preparador_audiencia.lexical_search import (
    needs_lexical_priority,
    search_chunks_lexical,
    search_persisted_lexical,
)
from preparador_audiencia.repositories import (
    ChunkRecord,
    ChunkRepository,
    ProcessoRepository,
)


def _chunk(chunk_id: int, page: int, text: str) -> ChunkRecord:
    return ChunkRecord(
        id=chunk_id,
        processo_id="proc_123",
        page_number=page,
        chunk_index=0,
        text=text,
        document_type=None,
        source_confidence="alta",
        vector_id=None,
        created_at="2026-07-26T12:00:00+00:00",
    )


def test_search_chunks_lexical_prioritizes_exact_judgment_terms() -> None:
    chunks = [
        _chunk(1, 1, "Discussao geral sobre o recurso especial."),
        _chunk(
            2,
            2,
            "A Terceira Turma julgou o recurso e decidiu dar parcial provimento.",
        ),
        _chunk(3, 3, "Relatorio com fatos anteriores ao julgamento."),
    ]

    results = search_chunks_lexical(
        chunks,
        "Qual foi o resultado do recurso e qual turma julgou?",
        top_k=2,
    )

    assert results[0].page_number == 2
    assert results[0].score == 1.0


def test_search_chunks_lexical_returns_empty_for_generic_question() -> None:
    chunks = [_chunk(1, 1, "Conteudo do processo.")]

    assert search_chunks_lexical(chunks, "O que foi isso?") == []


def test_needs_lexical_priority_for_exact_legal_information() -> None:
    assert needs_lexical_priority("Qual foi o resultado do julgamento?")
    assert needs_lexical_priority("Quem foi a relatora e qual a data?")
    assert not needs_lexical_priority("Explique os fatos alegados pela parte.")


def test_persisted_lexical_search_isolated_by_process(tmp_path) -> None:
    connection = connect_database(tmp_path / "test.sqlite3")
    initialize_database(connection)
    processos = ProcessoRepository(connection)
    processos.create_pending("proc_123", "a.pdf", "a.pdf", "a")
    processos.create_pending("proc_456", "b.pdf", "b.pdf", "b")
    chunks = ChunkRepository(connection)
    chunks.replace_for_processo(
        "proc_123",
        [TextChunk(1, 0, "Sentenca com parcial provimento.", "sentenca")],
    )
    chunks.replace_for_processo(
        "proc_456",
        [TextChunk(9, 0, "Sentenca sem provimento.", "sentenca")],
    )

    results = search_persisted_lexical(
        connection,
        processo_id="proc_123",
        pergunta="Qual foi o provimento?",
    )

    assert [result.page_number for result in results] == [1]


def test_persisted_lexical_index_tracks_chunk_replacement(tmp_path) -> None:
    connection = connect_database(tmp_path / "test.sqlite3")
    initialize_database(connection)
    ProcessoRepository(connection).create_pending(
        "proc_123",
        "a.pdf",
        "a.pdf",
        "a",
    )
    chunks = ChunkRepository(connection)
    chunks.replace_for_processo(
        "proc_123",
        [TextChunk(1, 0, "Medida protetiva deferida.", None)],
    )
    chunks.replace_for_processo(
        "proc_123",
        [TextChunk(2, 0, "Audiencia designada para agosto.", None)],
    )

    old_results = search_persisted_lexical(
        connection,
        processo_id="proc_123",
        pergunta="protetiva",
    )
    new_results = search_persisted_lexical(
        connection,
        processo_id="proc_123",
        pergunta="agosto",
    )

    assert old_results == []
    assert [result.page_number for result in new_results] == [2]


def test_database_migration_backfills_existing_chunks_fts(tmp_path) -> None:
    database_path = tmp_path / "test.sqlite3"
    connection = connect_database(database_path)
    initialize_database(connection)
    ProcessoRepository(connection).create_pending(
        "proc_123",
        "a.pdf",
        "a.pdf",
        "a",
    )
    ChunkRepository(connection).replace_for_processo(
        "proc_123",
        [TextChunk(4, 0, "Laudo pericial conclusivo.", None)],
    )
    connection.execute(f"DROP TABLE {process_fts_table_name('proc_123')}")

    results = search_persisted_lexical(
        connection,
        processo_id="proc_123",
        pergunta="laudo pericial",
    )
    assert [result.page_number for result in results] == [4]
    connection.close()

    reopened = connect_database(database_path)
    persisted_results = search_persisted_lexical(
        reopened,
        processo_id="proc_123",
        pergunta="laudo pericial",
    )

    assert [result.page_number for result in persisted_results] == [4]
