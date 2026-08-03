from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.repositories import ProcessoRepository, utc_now_text
from preparador_audiencia.retrieval import (
    index_process_chunks_configured,
    search_process_configured,
    search_process_pattern_anchors,
    search_process_queries_configured,
)
from preparador_audiencia.search import SearchResult


def test_index_process_chunks_configured_uses_ensemble(monkeypatch) -> None:
    calls = []
    chunk_repository = object()

    def fake_index(processo_id, chunks, model_specs):
        calls.append((processo_id, chunks, model_specs))
        return 7

    monkeypatch.setattr("preparador_audiencia.retrieval.index_process_chunks_ensemble", fake_index)

    result = index_process_chunks_configured(
        processo_id="proc_123",
        chunks=chunk_repository,
        embedding_spec="legal-ensemble",
    )

    assert result == 7
    assert calls[0][0] == "proc_123"
    assert calls[0][1] is chunk_repository
    assert calls[0][2] == ["jurisbert", "legal-bertimbau"]


def test_search_process_configured_uses_ensemble(monkeypatch) -> None:
    calls = []
    expected = [SearchResult("Trecho", 1, 0, None, 0.9)]

    def fake_search(processo_id, pergunta, top_k, model_specs):
        calls.append((processo_id, pergunta, top_k, model_specs))
        return expected

    monkeypatch.setattr("preparador_audiencia.retrieval.search_process_ensemble", fake_search)

    result = search_process_configured(
        processo_id="proc_123",
        pergunta="qual audiencia?",
        top_k=3,
        embedding_spec="legal-ensemble",
    )

    assert result == expected
    assert calls == [
        (
            "proc_123",
            "qual audiencia?",
            3,
            ["jurisbert", "legal-bertimbau"],
        )
    ]


def test_search_process_queries_configured_fuses_raw_and_routed_results(
    monkeypatch,
) -> None:
    calls: list[tuple[str, int]] = []

    def fake_search(**kwargs) -> list[SearchResult]:
        query = kwargs["pergunta"]
        calls.append((query, kwargs["top_k"]))
        if query == "pergunta original":
            return [
                SearchResult("Trecho original 1", 1, 0, None, 0.9),
                SearchResult("Trecho compartilhado", 2, 0, None, 0.8),
                SearchResult("Trecho original 3", 3, 0, None, 0.7),
            ]
        return [
            SearchResult("Trecho compartilhado", 2, 0, None, 0.95),
            SearchResult("Trecho roteado", 4, 0, None, 0.9),
        ]

    monkeypatch.setattr(
        "preparador_audiencia.retrieval.search_process_configured",
        fake_search,
    )

    results = search_process_queries_configured(
        processo_id="proc_123",
        queries=[
            ("pergunta original", 1.0),
            ("pergunta enriquecida", 0.35),
        ],
        top_k=3,
        embedding_spec="legal-ensemble",
    )

    assert calls == [
        ("pergunta original", 12),
        ("pergunta enriquecida", 12),
    ]
    assert [(result.page_number, result.chunk_index) for result in results] == [
        (2, 0),
        (1, 0),
        (3, 0),
    ]
    assert results[0].score > results[1].score


def test_search_process_queries_configured_deduplicates_equal_queries(
    monkeypatch,
) -> None:
    calls = []
    expected = [SearchResult("Trecho", 1, 0, None, 0.9)]

    def fake_search(**kwargs) -> list[SearchResult]:
        calls.append(kwargs)
        return expected

    monkeypatch.setattr(
        "preparador_audiencia.retrieval.search_process_configured",
        fake_search,
    )

    results = search_process_queries_configured(
        processo_id="proc_123",
        queries=[("mesma pergunta", 1.0), ("mesma pergunta", 0.35)],
        top_k=5,
    )

    assert results == expected
    assert len(calls) == 1
    assert calls[0]["pergunta"] == "mesma pergunta"


def test_search_process_queries_prioritizes_exact_lexical_result(
    monkeypatch,
) -> None:
    semantic = [
        SearchResult("Contexto semantico", 1, 0, None, 0.9),
        SearchResult("Outro contexto", 2, 0, None, 0.8),
    ]
    lexical = [
        SearchResult("Resultado literal", 8, 0, "decisao", 1.0),
        SearchResult("Contexto literal", 1, 0, None, 0.5),
    ]
    monkeypatch.setattr(
        "preparador_audiencia.retrieval.search_process_configured",
        lambda **kwargs: semantic,
    )
    monkeypatch.setattr(
        "preparador_audiencia.retrieval.search_process_lexical",
        lambda **kwargs: lexical,
    )

    results = search_process_queries_configured(
        processo_id="proc_123",
        queries=[("Qual foi o resultado do julgamento?", 1.0)],
        top_k=2,
    )

    assert results[0].page_number == 8


def test_search_process_queries_includes_routed_exact_result(
    monkeypatch,
) -> None:
    def fake_hybrid(**kwargs) -> list[SearchResult]:
        if kwargs["pergunta"] == "pergunta original":
            return [
                SearchResult("Contexto original", 1, 0, None, 0.9),
                SearchResult("Outro contexto", 2, 0, None, 0.8),
            ]
        return [
            SearchResult("Resultado literal", 22, 0, "decisao", 1.0),
            SearchResult("Contexto expandido", 3, 0, None, 0.8),
        ]

    monkeypatch.setattr(
        "preparador_audiencia.retrieval._search_process_hybrid_configured",
        fake_hybrid,
    )

    results = search_process_queries_configured(
        processo_id="proc_123",
        queries=[
            ("pergunta original", 1.0),
            ("resultado decisao provimento", 0.35),
        ],
        top_k=2,
    )

    assert 22 in [result.page_number for result in results]


def test_pattern_anchors_find_markers_when_pdf_text_has_no_spaces(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "test.sqlite3"
    connection = connect_database(database_path)
    initialize_database(connection)
    ProcessoRepository(connection).create_pending(
        "proc_123",
        "processo.pdf",
        "storage/processo.pdf",
        "abc",
    )
    now = utc_now_text()
    connection.executemany(
        """
        INSERT INTO chunks (
            processo_id, page_number, chunk_index, text, document_type,
            source_confidence, vector_id, created_at
        ) VALUES (?, ?, ?, ?, NULL, 'alta', NULL, ?)
        """,
        [
            (
                "proc_123",
                5,
                0,
                "TERMODEDECLARACOESEMAUTODEPRISAOQUEPRESTAAVITIMA",
                now,
            ),
            ("proc_123", 5, 1, "QUEavitimarelatouosfatos", now),
        ],
    )
    connection.commit()
    connection.close()
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(database_path))

    results = search_process_pattern_anchors(
        "proc_123",
        (("termo de declaracoes", 1),),
        top_k=4,
    )

    assert [(result.page_number, result.chunk_index) for result in results] == [
        (5, 0),
        (5, 1),
    ]
