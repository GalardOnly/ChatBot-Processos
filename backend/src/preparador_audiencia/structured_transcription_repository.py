from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from preparador_audiencia.repositories import utc_now_text

TRANSCRIPTION_SCHEMA_VERSION = "2.0"


@dataclass(frozen=True)
class StructuredTranscriptionRecord:
    processo_id: str
    schema_version: str
    status: str
    payload: dict[str, object]
    created_at: str
    updated_at: str


class StructuredTranscriptionRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def get(self, processo_id: str) -> StructuredTranscriptionRecord | None:
        row = self.connection.execute(
            "SELECT * FROM structured_transcriptions WHERE processo_id = ?",
            (processo_id,),
        ).fetchone()
        return _record_from_row(row)

    def save(
        self,
        processo_id: str,
        *,
        status: str,
        payload: dict[str, object],
    ) -> StructuredTranscriptionRecord:
        now = utc_now_text()
        self.connection.execute(
            """
            INSERT INTO structured_transcriptions (
                processo_id, schema_version, status, payload_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(processo_id) DO UPDATE SET
                schema_version = excluded.schema_version,
                status = excluded.status,
                payload_json = excluded.payload_json,
                updated_at = excluded.updated_at
            """,
            (
                processo_id,
                TRANSCRIPTION_SCHEMA_VERSION,
                status,
                json.dumps(payload, ensure_ascii=False),
                now,
                now,
            ),
        )
        self.connection.commit()
        record = self.get(processo_id)
        if record is None:
            raise RuntimeError("transcricao salva nao pode ser carregada")
        return record

    def delete(self, processo_id: str) -> None:
        self.connection.execute(
            "DELETE FROM structured_transcriptions WHERE processo_id = ?",
            (processo_id,),
        )
        self.connection.commit()


def _record_from_row(row: sqlite3.Row | None) -> StructuredTranscriptionRecord | None:
    if row is None:
        return None
    payload = json.loads(str(row["payload_json"]))
    if not isinstance(payload, dict):
        raise ValueError("payload da transcricao estruturada deve ser um objeto")
    return StructuredTranscriptionRecord(
        processo_id=str(row["processo_id"]),
        schema_version=str(row["schema_version"]),
        status=str(row["status"]),
        payload=payload,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )
