from __future__ import annotations

import sqlite3
from hashlib import sha256


def process_fts_table_name(processo_id: str) -> str:
    digest = sha256(processo_id.encode("utf-8")).hexdigest()[:24]
    return f"chunks_fts_{digest}"


def ensure_process_fts(
    connection: sqlite3.Connection,
    processo_id: str,
    *,
    commit_backfill: bool = False,
) -> str:
    table_name = process_fts_table_name(processo_id)
    exists = (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        is not None
    )
    connection.execute(
        f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS {table_name} USING fts5(
            text,
            tokenize='unicode61 remove_diacritics 2'
        )
        """
    )
    if not exists:
        connection.execute(
            f"""
            INSERT INTO {table_name}(rowid, text)
            SELECT id, text
            FROM chunks
            WHERE processo_id = ?
            """,
            (processo_id,),
        )
        if commit_backfill:
            connection.commit()
    return table_name


def replace_process_fts(
    connection: sqlite3.Connection,
    processo_id: str,
) -> None:
    table_name = ensure_process_fts(connection, processo_id)
    connection.execute(f"DELETE FROM {table_name}")
    connection.execute(
        f"""
        INSERT INTO {table_name}(rowid, text)
        SELECT id, text
        FROM chunks
        WHERE processo_id = ?
        """,
        (processo_id,),
    )
