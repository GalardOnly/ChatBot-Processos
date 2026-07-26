from __future__ import annotations

import re
import sqlite3
import unicodedata

from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.repositories import ChunkRecord, ChunkRepository
from preparador_audiencia.search import SearchResult

MIN_TOKEN_LENGTH = 3
STOPWORDS = {
    "ainda",
    "algum",
    "alguma",
    "antes",
    "caso",
    "como",
    "deve",
    "deveria",
    "disso",
    "documento",
    "durante",
    "essa",
    "esse",
    "esta",
    "este",
    "fazer",
    "foi",
    "isso",
    "neste",
    "onde",
    "para",
    "pela",
    "pelo",
    "pode",
    "processo",
    "qual",
    "quais",
    "quando",
    "quem",
    "sobre",
    "uma",
    "que",
}
PRECISION_TERMS = {
    "data",
    "decisao",
    "numero",
    "prazo",
    "resultado",
    "valor",
}


def search_process_lexical(
    processo_id: str,
    pergunta: str,
    top_k: int = 5,
) -> list[SearchResult]:
    connection = connect_database()
    initialize_database(connection)
    try:
        chunks = ChunkRepository(connection).list_for_processo(processo_id)
    finally:
        connection.close()
    return search_chunks_lexical(chunks, pergunta, top_k)


def search_chunks_lexical(
    chunks: list[ChunkRecord],
    pergunta: str,
    top_k: int = 5,
) -> list[SearchResult]:
    tokens = _query_tokens(pergunta)
    if not chunks or not tokens or top_k <= 0:
        return []

    by_id = {chunk.id: chunk for chunk in chunks}
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute(
            "CREATE VIRTUAL TABLE docs USING fts5("
            "text, tokenize='unicode61 remove_diacritics 2')"
        )
        connection.executemany(
            "INSERT INTO docs(rowid, text) VALUES (?, ?)",
            [(chunk.id, chunk.text) for chunk in chunks],
        )
        query = " OR ".join(f'"{token}"' for token in tokens)
        rows = connection.execute(
            """
            SELECT rowid, bm25(docs) AS lexical_rank
            FROM docs
            WHERE docs MATCH ?
            ORDER BY lexical_rank
            LIMIT ?
            """,
            (query, top_k),
        ).fetchall()
    finally:
        connection.close()

    results = []
    for rank, row in enumerate(rows, start=1):
        chunk = by_id[int(row[0])]
        results.append(
            SearchResult(
                text=chunk.text,
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
                document_type=chunk.document_type,
                score=round(1.0 / rank, 4),
            )
        )
    return results


def needs_lexical_priority(text: str) -> bool:
    return bool(set(_query_tokens(text)).intersection(PRECISION_TERMS))


def _query_tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", text.lower().replace("_", " "))
    without_accents = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return sorted(
        {
            token
            for token in re.findall(r"[a-z0-9]+", without_accents)
            if len(token) >= MIN_TOKEN_LENGTH and token not in STOPWORDS
        }
    )
