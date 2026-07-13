from __future__ import annotations

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

