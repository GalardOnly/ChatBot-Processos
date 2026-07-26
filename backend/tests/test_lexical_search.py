from preparador_audiencia.lexical_search import (
    needs_lexical_priority,
    search_chunks_lexical,
)
from preparador_audiencia.repositories import ChunkRecord


def _chunk(chunk_id: int, page: int, text: str) -> ChunkRecord:
    return ChunkRecord(
        id=chunk_id,
        processo_id="proc_123",
        page_number=page,
        chunk_index=0,
        text=text,
        document_type=None,
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
