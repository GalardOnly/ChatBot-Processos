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
            progress_stage TEXT NOT NULL DEFAULT 'aguardando',
            progress_current INTEGER NOT NULL DEFAULT 0,
            progress_total INTEGER NOT NULL DEFAULT 0,
            progress_message TEXT,
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
            source_confidence TEXT NOT NULL DEFAULT 'desconhecida',
            ocr_engine TEXT,
            ocr_engine_version TEXT,
            ocr_device TEXT,
            ocr_cache_hit INTEGER NOT NULL DEFAULT 0,
            ocr_fallback_used INTEGER NOT NULL DEFAULT 0,
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

        CREATE TABLE IF NOT EXISTS hearing_dossiers (
            processo_id TEXT PRIMARY KEY REFERENCES processos(id) ON DELETE CASCADE,
            schema_version TEXT NOT NULL,
            status TEXT NOT NULL,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS hearing_dossier_sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            processo_id TEXT NOT NULL REFERENCES hearing_dossiers(processo_id)
                ON DELETE CASCADE,
            section_key TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT,
            model TEXT,
            fallback_used INTEGER NOT NULL DEFAULT 0,
            retrieval_ms INTEGER,
            generation_ms INTEGER,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (processo_id, section_key)
        );

        CREATE TABLE IF NOT EXISTS structured_transcriptions (
            processo_id TEXT PRIMARY KEY REFERENCES processos(id) ON DELETE CASCADE,
            schema_version TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS testimony_comparisons (
            id TEXT PRIMARY KEY,
            processo_id TEXT NOT NULL REFERENCES processos(id) ON DELETE CASCADE,
            testimony_a_id TEXT NOT NULL,
            testimony_b_id TEXT NOT NULL,
            transcription_schema_version TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            model TEXT NOT NULL,
            fallback_used INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS testimony_question_guides (
            id TEXT PRIMARY KEY,
            processo_id TEXT NOT NULL REFERENCES processos(id) ON DELETE CASCADE,
            testimony_id TEXT NOT NULL,
            transcription_schema_version TEXT NOT NULL,
            comparison_fingerprint TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            model TEXT NOT NULL,
            fallback_used INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS prescription_calculations (
            id TEXT PRIMARY KEY,
            processo_id TEXT NOT NULL REFERENCES processos(id) ON DELETE CASCADE,
            schema_version TEXT NOT NULL,
            legal_ruleset_version TEXT NOT NULL,
            input_json TEXT NOT NULL,
            result_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS judgment_structures (
            processo_id TEXT PRIMARY KEY REFERENCES processos(id) ON DELETE CASCADE,
            schema_version TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS defense_theses (
            processo_id TEXT PRIMARY KEY REFERENCES processos(id) ON DELETE CASCADE,
            schema_version TEXT NOT NULL,
            catalog_version TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            model TEXT NOT NULL,
            fallback_used INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS nullity_analyses (
            processo_id TEXT NOT NULL REFERENCES processos(id) ON DELETE CASCADE,
            topic_id TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            catalog_version TEXT NOT NULL,
            conclusion TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            model TEXT NOT NULL,
            fallback_used INTEGER NOT NULL DEFAULT 0,
            search_mode TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (processo_id, topic_id)
        );
        """
    )
    _ensure_process_columns(connection)
    _ensure_chunk_columns(connection)
    _ensure_chat_message_columns(connection)
    _ensure_hearing_dossier_section_columns(connection)
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_processos_sha256_status ON processos (sha256, status)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_dossier_sections_processo_status "
        "ON hearing_dossier_sections (processo_id, status)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_testimony_comparisons_process "
        "ON testimony_comparisons (processo_id, testimony_a_id, testimony_b_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_testimony_question_guides_process "
        "ON testimony_question_guides (processo_id, testimony_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_prescription_calculations_process "
        "ON prescription_calculations (processo_id, created_at DESC)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_nullity_analyses_process "
        "ON nullity_analyses (processo_id, updated_at DESC)"
    )
    connection.execute(
        """
        UPDATE processos
        SET progress_stage = 'concluido',
            progress_current = 1,
            progress_total = 1,
            progress_message = 'Processo pronto para consulta'
        WHERE status = 'concluido' AND progress_stage = 'aguardando'
        """
    )
    connection.commit()


def _ensure_process_columns(connection: sqlite3.Connection) -> None:
    columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(processos)").fetchall()
    }
    migrations = {
        "progress_stage": (
            "ALTER TABLE processos ADD COLUMN progress_stage "
            "TEXT NOT NULL DEFAULT 'aguardando'"
        ),
        "progress_current": (
            "ALTER TABLE processos ADD COLUMN progress_current INTEGER NOT NULL DEFAULT 0"
        ),
        "progress_total": (
            "ALTER TABLE processos ADD COLUMN progress_total INTEGER NOT NULL DEFAULT 0"
        ),
        "progress_message": "ALTER TABLE processos ADD COLUMN progress_message TEXT",
    }
    for column, statement in migrations.items():
        if column not in columns:
            connection.execute(statement)


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


def _ensure_chunk_columns(connection: sqlite3.Connection) -> None:
    columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(chunks)").fetchall()
    }
    migrations = {
        "source_confidence": (
            "ALTER TABLE chunks ADD COLUMN source_confidence "
            "TEXT NOT NULL DEFAULT 'desconhecida'"
        ),
        "ocr_engine": "ALTER TABLE chunks ADD COLUMN ocr_engine TEXT",
        "ocr_engine_version": (
            "ALTER TABLE chunks ADD COLUMN ocr_engine_version TEXT"
        ),
        "ocr_device": "ALTER TABLE chunks ADD COLUMN ocr_device TEXT",
        "ocr_cache_hit": (
            "ALTER TABLE chunks ADD COLUMN ocr_cache_hit INTEGER NOT NULL DEFAULT 0"
        ),
        "ocr_fallback_used": (
            "ALTER TABLE chunks ADD COLUMN ocr_fallback_used "
            "INTEGER NOT NULL DEFAULT 0"
        ),
    }
    for column, statement in migrations.items():
        if column not in columns:
            connection.execute(statement)


def _ensure_hearing_dossier_section_columns(connection: sqlite3.Connection) -> None:
    columns = {
        str(row["name"])
        for row in connection.execute(
            "PRAGMA table_info(hearing_dossier_sections)"
        ).fetchall()
    }
    migrations = {
        "retrieval_ms": (
            "ALTER TABLE hearing_dossier_sections ADD COLUMN retrieval_ms INTEGER"
        ),
        "generation_ms": (
            "ALTER TABLE hearing_dossier_sections ADD COLUMN generation_ms INTEGER"
        ),
    }
    for column, statement in migrations.items():
        if column not in columns:
            connection.execute(statement)
