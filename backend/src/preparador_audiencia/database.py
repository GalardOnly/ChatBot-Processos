from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DEFAULT_DATABASE_PATH = ".preparador-audiencia.sqlite3"


def database_path_from_environment() -> str:
    return os.getenv("PREPARADOR_DATABASE_PATH", DEFAULT_DATABASE_PATH)


def connect_database(path: str | Path | None = None) -> sqlite3.Connection:
    database_path = str(path) if path is not None else database_path_from_environment()
    connection = sqlite3.connect(database_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS processos (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            status TEXT NOT NULL,
            page_count INTEGER NOT NULL DEFAULT 0,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            processo_id TEXT NOT NULL REFERENCES processos(id) ON DELETE CASCADE,
            page_number INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            document_type TEXT,
            vector_id TEXT,
            created_at TEXT NOT NULL,
            UNIQUE (processo_id, page_number, chunk_index)
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            processo_id TEXT NOT NULL REFERENCES processos(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            model TEXT,
            latency_ms INTEGER,
            error TEXT,
            retrieved_pages_json TEXT,
            retrieved_chunks_json TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS quality_evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            processo_id TEXT NOT NULL REFERENCES processos(id) ON DELETE CASCADE,
            pergunta TEXT NOT NULL,
            resposta TEXT NOT NULL,
            evaluator_model TEXT NOT NULL,
            generator_model TEXT,
            fidelidade_fontes INTEGER NOT NULL,
            completude_juridica INTEGER NOT NULL,
            utilidade_audiencia INTEGER NOT NULL,
            risco_alucinacao TEXT NOT NULL,
            pontos_fortes_json TEXT NOT NULL,
            problemas_json TEXT NOT NULL,
            faltou_json TEXT NOT NULL,
            veredito TEXT NOT NULL,
            raw_response TEXT NOT NULL,
            error TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    _ensure_chat_message_columns(connection)
    connection.commit()


def _ensure_chat_message_columns(connection: sqlite3.Connection) -> None:
    columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(chat_messages)").fetchall()
    }
    migrations = {
        "model": "ALTER TABLE chat_messages ADD COLUMN model TEXT",
        "latency_ms": "ALTER TABLE chat_messages ADD COLUMN latency_ms INTEGER",
        "error": "ALTER TABLE chat_messages ADD COLUMN error TEXT",
    }
    for column, statement in migrations.items():
        if column not in columns:
            connection.execute(statement)
