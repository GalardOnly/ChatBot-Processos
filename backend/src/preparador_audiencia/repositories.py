from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from preparador_audiencia.chunking import TextChunk


@dataclass(frozen=True)
class ProcessoRecord:
    id: str
    filename: str
    file_path: str
    sha256: str
    status: str
    page_count: int
    chunk_count: int
    error_message: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ChunkRecord:
    id: int
    processo_id: str
    page_number: int
    chunk_index: int
    text: str
    document_type: str | None
    vector_id: str | None
    created_at: str


@dataclass(frozen=True)
class ChatMessageRecord:
    id: int
    processo_id: str
    role: str
    content: str
    model: str | None
    latency_ms: int | None
    error: str | None
    retrieved_pages: list[int]
    retrieved_chunks: list[dict[str, object]]
    created_at: str


def utc_now_text() -> str:
    return datetime.now(UTC).isoformat()


def _processo_from_row(row: sqlite3.Row | None) -> ProcessoRecord | None:
    if row is None:
        return None
    return ProcessoRecord(
        id=str(row["id"]),
        filename=str(row["filename"]),
        file_path=str(row["file_path"]),
        sha256=str(row["sha256"]),
        status=str(row["status"]),
        page_count=int(row["page_count"]),
        chunk_count=int(row["chunk_count"]),
        error_message=row["error_message"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _chunk_from_row(row: sqlite3.Row) -> ChunkRecord:
    return ChunkRecord(
        id=int(row["id"]),
        processo_id=str(row["processo_id"]),
        page_number=int(row["page_number"]),
        chunk_index=int(row["chunk_index"]),
        text=str(row["text"]),
        document_type=row["document_type"],
        vector_id=row["vector_id"],
        created_at=str(row["created_at"]),
    )


def _chat_message_from_row(row: sqlite3.Row) -> ChatMessageRecord:
    return ChatMessageRecord(
        id=int(row["id"]),
        processo_id=str(row["processo_id"]),
        role=str(row["role"]),
        content=str(row["content"]),
        model=row["model"],
        latency_ms=row["latency_ms"],
        error=row["error"],
        retrieved_pages=json.loads(row["retrieved_pages_json"] or "[]"),
        retrieved_chunks=json.loads(row["retrieved_chunks_json"] or "[]"),
        created_at=str(row["created_at"]),
    )


class ProcessoRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create_pending(
        self,
        processo_id: str,
        filename: str,
        file_path: str,
        sha256_digest: str,
    ) -> ProcessoRecord:
        now = utc_now_text()
        self.connection.execute(
            """
            INSERT INTO processos (
                id, filename, file_path, sha256, status, page_count, chunk_count,
                error_message, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 0, 0, NULL, ?, ?)
            """,
            (processo_id, filename, file_path, sha256_digest, "pendente", now, now),
        )
        self.connection.commit()
        processo = self.get(processo_id)
        if processo is None:
            raise RuntimeError("processo criado nao pode ser carregado")
        return processo

    def get(self, processo_id: str) -> ProcessoRecord | None:
        row = self.connection.execute(
            "SELECT * FROM processos WHERE id = ?",
            (processo_id,),
        ).fetchone()
        return _processo_from_row(row)

    def list_recent(self, limit: int = 10) -> list[ProcessoRecord]:
        rows = self.connection.execute(
            """
            SELECT *
            FROM processos
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            processo
            for row in rows
            if (processo := _processo_from_row(row)) is not None
        ]

    def mark_processing(self, processo_id: str) -> None:
        self.connection.execute(
            """
            UPDATE processos
            SET status = ?, error_message = NULL, updated_at = ?
            WHERE id = ?
            """,
            ("processando", utc_now_text(), processo_id),
        )
        self.connection.commit()

    def mark_completed(self, processo_id: str, page_count: int, chunk_count: int) -> None:
        self.connection.execute(
            """
            UPDATE processos
            SET status = ?, page_count = ?, chunk_count = ?, error_message = NULL, updated_at = ?
            WHERE id = ?
            """,
            ("concluido", page_count, chunk_count, utc_now_text(), processo_id),
        )
        self.connection.commit()

    def mark_error(self, processo_id: str, message: str) -> None:
        self.connection.execute(
            """
            UPDATE processos
            SET status = ?, error_message = ?, updated_at = ?
            WHERE id = ?
            """,
            ("erro", message, utc_now_text(), processo_id),
        )
        self.connection.commit()


class ChunkRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def replace_for_processo(self, processo_id: str, chunks: list[TextChunk]) -> None:
        now = utc_now_text()
        self.connection.execute("DELETE FROM chunks WHERE processo_id = ?", (processo_id,))
        self.connection.executemany(
            """
            INSERT INTO chunks (
                processo_id, page_number, chunk_index, text, document_type, vector_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, NULL, ?)
            """,
            [
                (
                    processo_id,
                    chunk.page_number,
                    chunk.chunk_index,
                    chunk.text,
                    chunk.document_type,
                    now,
                )
                for chunk in chunks
            ],
        )
        self.connection.commit()

    def count_for_processo(self, processo_id: str) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) AS total FROM chunks WHERE processo_id = ?",
            (processo_id,),
        ).fetchone()
        return int(row["total"])

    def list_for_processo(self, processo_id: str) -> list[ChunkRecord]:
        rows = self.connection.execute(
            """
            SELECT *
            FROM chunks
            WHERE processo_id = ?
            ORDER BY page_number, chunk_index
            """,
            (processo_id,),
        ).fetchall()
        return [_chunk_from_row(row) for row in rows]

    def update_vector_ids(self, vector_ids_by_chunk_id: dict[int, str]) -> None:
        if not vector_ids_by_chunk_id:
            return
        self.connection.executemany(
            "UPDATE chunks SET vector_id = ? WHERE id = ?",
            [(vector_id, chunk_id) for chunk_id, vector_id in vector_ids_by_chunk_id.items()],
        )
        self.connection.commit()


class ChatMessageRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def add(
        self,
        processo_id: str,
        role: str,
        content: str,
        *,
        model: str | None = None,
        latency_ms: int | None = None,
        error: str | None = None,
        retrieved_pages: list[int] | None = None,
        retrieved_chunks: list[dict[str, object]] | None = None,
    ) -> ChatMessageRecord:
        now = utc_now_text()
        self.connection.execute(
            """
            INSERT INTO chat_messages (
                processo_id, role, content, model, latency_ms, error,
                retrieved_pages_json, retrieved_chunks_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                processo_id,
                role,
                content,
                model,
                latency_ms,
                error,
                json.dumps(retrieved_pages or []),
                json.dumps(retrieved_chunks or []),
                now,
            ),
        )
        self.connection.commit()
        row = self.connection.execute(
            "SELECT * FROM chat_messages WHERE id = last_insert_rowid()"
        ).fetchone()
        return _chat_message_from_row(row)

    def list_for_processo(self, processo_id: str) -> list[ChatMessageRecord]:
        rows = self.connection.execute(
            """
            SELECT *
            FROM chat_messages
            WHERE processo_id = ?
            ORDER BY id
            """,
            (processo_id,),
        ).fetchall()
        return [_chat_message_from_row(row) for row in rows]
