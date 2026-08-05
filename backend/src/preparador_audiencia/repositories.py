from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from preparador_audiencia.chunking import TextChunk
from preparador_audiencia.lexical_index import replace_process_fts

if TYPE_CHECKING:
    from preparador_audiencia.quality import LegalQualityEvaluation


@dataclass(frozen=True)
class ProcessoRecord:
    id: str
    filename: str
    file_path: str
    sha256: str
    status: str
    page_count: int
    chunk_count: int
    progress_stage: str
    progress_current: int
    progress_total: int
    progress_message: str | None
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
    source_confidence: str
    vector_id: str | None
    created_at: str
    ocr_engine: str | None = None
    ocr_engine_version: str | None = None
    ocr_device: str | None = None
    ocr_cache_hit: bool = False
    ocr_fallback_used: bool = False


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
        progress_stage=str(row["progress_stage"]),
        progress_current=int(row["progress_current"]),
        progress_total=int(row["progress_total"]),
        progress_message=row["progress_message"],
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
        source_confidence=str(row["source_confidence"]),
        vector_id=row["vector_id"],
        created_at=str(row["created_at"]),
        ocr_engine=row["ocr_engine"],
        ocr_engine_version=row["ocr_engine_version"],
        ocr_device=row["ocr_device"],
        ocr_cache_hit=bool(row["ocr_cache_hit"]),
        ocr_fallback_used=bool(row["ocr_fallback_used"]),
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

    def find_reusable_by_sha256(self, sha256_digest: str) -> ProcessoRecord | None:
        row = self.connection.execute(
            """
            SELECT *
            FROM processos
            WHERE sha256 = ?
              AND status IN ('concluido', 'processando', 'pendente')
            ORDER BY
                CASE status
                    WHEN 'concluido' THEN 0
                    WHEN 'processando' THEN 1
                    ELSE 2
                END,
                updated_at DESC
            LIMIT 1
            """,
            (sha256_digest,),
        ).fetchone()
        return _processo_from_row(row)

    def mark_processing(self, processo_id: str) -> None:
        self.connection.execute(
            """
            UPDATE processos
            SET status = ?, progress_stage = ?, progress_current = 0,
                progress_total = 0, progress_message = ?,
                error_message = NULL, updated_at = ?
            WHERE id = ?
            """,
            (
                "processando",
                "iniciando",
                "Preparando o processamento",
                utc_now_text(),
                processo_id,
            ),
        )
        self.connection.commit()

    def update_progress(
        self,
        processo_id: str,
        *,
        stage: str,
        current: int,
        total: int,
        message: str,
        page_count: int | None = None,
        chunk_count: int | None = None,
    ) -> None:
        assignments = [
            "progress_stage = ?",
            "progress_current = ?",
            "progress_total = ?",
            "progress_message = ?",
            "updated_at = ?",
        ]
        values: list[object] = [
            stage,
            max(0, current),
            max(0, total),
            message,
            utc_now_text(),
        ]
        if page_count is not None:
            assignments.append("page_count = ?")
            values.append(max(0, page_count))
        if chunk_count is not None:
            assignments.append("chunk_count = ?")
            values.append(max(0, chunk_count))
        values.append(processo_id)
        self.connection.execute(
            f"UPDATE processos SET {', '.join(assignments)} WHERE id = ?",
            values,
        )
        self.connection.commit()

    def mark_completed(self, processo_id: str, page_count: int, chunk_count: int) -> None:
        self.connection.execute(
            """
            UPDATE processos
            SET status = ?, page_count = ?, chunk_count = ?,
                progress_stage = ?, progress_current = 1, progress_total = 1,
                progress_message = ?, error_message = NULL, updated_at = ?
            WHERE id = ?
            """,
            (
                "concluido",
                page_count,
                chunk_count,
                "concluido",
                "Processo pronto para consulta",
                utc_now_text(),
                processo_id,
            ),
        )
        self.connection.commit()

    def mark_error(self, processo_id: str, message: str) -> None:
        self.connection.execute(
            """
            UPDATE processos
            SET status = ?, progress_stage = ?, progress_message = ?,
                error_message = ?, updated_at = ?
            WHERE id = ?
            """,
            ("erro", "erro", "Falha no processamento", message, utc_now_text(), processo_id),
        )
        self.connection.commit()

    def mark_pending_for_reprocessing(self, processo_id: str) -> None:
        self.connection.execute(
            """
            UPDATE processos
            SET status = ?, progress_stage = ?, progress_current = 0,
                progress_total = 0, progress_message = ?,
                error_message = NULL, updated_at = ?
            WHERE id = ?
            """,
            (
                "pendente",
                "reprocessamento_pendente",
                "Aguardando reprocessamento da extracao",
                utc_now_text(),
                processo_id,
            ),
        )
        self.connection.commit()


class ChunkRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def replace_for_processo(self, processo_id: str, chunks: list[TextChunk]) -> None:
        now = utc_now_text()
        self.connection.execute(
            "DELETE FROM nullity_analyses WHERE processo_id = ?",
            (processo_id,),
        )
        self.connection.execute(
            "DELETE FROM defense_theses WHERE processo_id = ?",
            (processo_id,),
        )
        self.connection.execute(
            "DELETE FROM judgment_structures WHERE processo_id = ?",
            (processo_id,),
        )
        self.connection.execute(
            "DELETE FROM prescription_calculations WHERE processo_id = ?",
            (processo_id,),
        )
        self.connection.execute(
            "DELETE FROM testimony_question_guides WHERE processo_id = ?",
            (processo_id,),
        )
        self.connection.execute(
            "DELETE FROM testimony_comparisons WHERE processo_id = ?",
            (processo_id,),
        )
        self.connection.execute(
            "DELETE FROM structured_transcriptions WHERE processo_id = ?",
            (processo_id,),
        )
        self.connection.execute("DELETE FROM chunks WHERE processo_id = ?", (processo_id,))
        self.connection.executemany(
            """
            INSERT INTO chunks (
                processo_id, page_number, chunk_index, text, document_type,
                source_confidence, ocr_engine, ocr_engine_version, ocr_device,
                ocr_cache_hit, ocr_fallback_used, vector_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
            """,
            [
                (
                    processo_id,
                    chunk.page_number,
                    chunk.chunk_index,
                    chunk.text,
                    chunk.document_type,
                    chunk.source_confidence,
                    chunk.ocr_engine,
                    chunk.ocr_engine_version,
                    chunk.ocr_device,
                    int(chunk.ocr_cache_hit),
                    int(chunk.ocr_fallback_used),
                    now,
                )
                for chunk in chunks
            ],
        )
        replace_process_fts(self.connection, processo_id)
        self.connection.commit()

    def count_for_processo(self, processo_id: str) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) AS total FROM chunks WHERE processo_id = ?",
            (processo_id,),
        ).fetchone()
        return int(row["total"])

    def has_unknown_confidence(self, processo_id: str) -> bool:
        row = self.connection.execute(
            """
            SELECT EXISTS(
                SELECT 1
                FROM chunks
                WHERE processo_id = ?
                  AND source_confidence = 'desconhecida'
            ) AS found
            """,
            (processo_id,),
        ).fetchone()
        return bool(row["found"])

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


class QualityEvaluationRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def add(
        self,
        processo_id: str,
        pergunta: str,
        resposta: str,
        evaluation: LegalQualityEvaluation,
        *,
        generator_model: str | None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO quality_evaluations (
                processo_id, pergunta, resposta, evaluator_model, generator_model,
                fidelidade_fontes, completude_juridica, utilidade_audiencia,
                risco_alucinacao, pontos_fortes_json, problemas_json, faltou_json,
                veredito, raw_response, error, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                processo_id,
                pergunta,
                resposta,
                evaluation.evaluator_model,
                generator_model,
                evaluation.fidelidade_fontes,
                evaluation.completude_juridica,
                evaluation.utilidade_audiencia,
                evaluation.risco_alucinacao,
                json.dumps(evaluation.pontos_fortes, ensure_ascii=False),
                json.dumps(evaluation.problemas, ensure_ascii=False),
                json.dumps(evaluation.faltou, ensure_ascii=False),
                evaluation.veredito,
                evaluation.raw_response,
                evaluation.error,
                utc_now_text(),
            ),
        )
        self.connection.commit()
