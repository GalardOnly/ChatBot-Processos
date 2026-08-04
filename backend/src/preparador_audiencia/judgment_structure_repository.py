from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from preparador_audiencia.judgment_structure import JUDGMENT_STRUCTURE_SCHEMA_VERSION
from preparador_audiencia.repositories import utc_now_text


@dataclass(frozen=True)
class JudgmentStructureRecord:
    processo_id: str
    schema_version: str
    status: str
    payload: dict[str, object]
    created_at: str
    updated_at: str


class JudgmentStructureRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def get(self, processo_id: str) -> JudgmentStructureRecord | None:
        row = self.connection.execute(
            "SELECT * FROM judgment_structures WHERE processo_id = ?",
            (processo_id,),
        ).fetchone()
        return _record_from_row(row)

    def save(
        self,
        processo_id: str,
        *,
        status: str,
        payload: dict[str, object],
    ) -> JudgmentStructureRecord:
        now = utc_now_text()
        self.connection.execute(
            """
            INSERT INTO judgment_structures (
                processo_id, schema_version, status, payload_json,
                created_at, updated_at
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
                JUDGMENT_STRUCTURE_SCHEMA_VERSION,
                status,
                json.dumps(payload, ensure_ascii=False),
                now,
                now,
            ),
        )
        self.connection.commit()
        record = self.get(processo_id)
        if record is None:
            raise RuntimeError("estrutura de sentenca salva nao pode ser carregada")
        return record


def _record_from_row(row: sqlite3.Row | None) -> JudgmentStructureRecord | None:
    if row is None:
        return None
    payload = json.loads(str(row["payload_json"]))
    if not isinstance(payload, dict):
        raise ValueError("payload da estrutura de sentenca deve ser um objeto")
    return JudgmentStructureRecord(
        processo_id=str(row["processo_id"]),
        schema_version=str(row["schema_version"]),
        status=str(row["status"]),
        payload=payload,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )
