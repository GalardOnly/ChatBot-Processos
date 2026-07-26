from __future__ import annotations

import re
import sqlite3
import unicodedata

from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.lexical_index import ensure_process_fts
from preparador_audiencia.repositories import ChunkRecord
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
        return search_persisted_lexical(
            connection,
            processo_id=processo_id,
            pergunta=pergunta,
            top_k=top_k,
        )
    finally:
        connection.close()


def search_persisted_lexical(
    connection: sqlite3.Connection,
    *,
    processo_id: str,
    pergunta: str,
    top_k: int = 5,
) -> list[SearchResult]:
    tokens = _query_tokens(pergunta)
    if not tokens or top_k <= 0:
        return []

    query = _match_query(tokens)
    table_name = ensure_process_fts(
        connection,
        processo_id,
        commit_backfill=True,
    )
    rows = connection.execute(
        f"""
        SELECT chunks.text, chunks.page_number, chunks.chunk_index,
               chunks.document_type, bm25({table_name}) AS lexical_rank
        FROM {table_name}
        JOIN chunks ON chunks.id = {table_name}.rowid
        WHERE {table_name} MATCH ?
        ORDER BY lexical_rank
        LIMIT ?
        """,
        (query, top_k),
    ).fetchall()
    return [
        SearchResult(
            text=str(row["text"]),
            page_number=int(row["page_number"]),
            chunk_index=int(row["chunk_index"]),
            document_type=row["document_type"],
            score=round(1.0 / rank, 4),
        )
        for rank, row in enumerate(rows, start=1)
    ]


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
        query = _match_query(tokens)
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


def _match_query(tokens: list[str]) -> str:
    return " OR ".join(f'"{token}"' for token in tokens)


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
