from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from preparador_audiencia.repositories import utc_now_text

DEFENSE_THESES_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class DefenseThesesRecord:
    processo_id: str
    schema_version: str
    catalog_version: str
    status: str
    payload: dict[str, object]
    model: str
    fallback_used: bool
    created_at: str
    updated_at: str


class DefenseThesesRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def get(self, processo_id: str) -> DefenseThesesRecord | None:
        row = self.connection.execute(
            "SELECT * FROM defense_theses WHERE processo_id = ?",
            (processo_id,),
        ).fetchone()
        return _record_from_row(row)

    def save(
        self,
        processo_id: str,
        *,
        catalog_version: str,
        status: str,
        payload: dict[str, object],
        model: str,
        fallback_used: bool,
    ) -> DefenseThesesRecord:
        now = utc_now_text()
        self.connection.execute(
            """
            INSERT INTO defense_theses (
                processo_id, schema_version, catalog_version, status,
                payload_json, model, fallback_used, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(processo_id) DO UPDATE SET
                schema_version = excluded.schema_version,
                catalog_version = excluded.catalog_version,
                status = excluded.status,
                payload_json = excluded.payload_json,
                model = excluded.model,
                fallback_used = excluded.fallback_used,
                updated_at = excluded.updated_at
            """,
            (
                processo_id,
                DEFENSE_THESES_SCHEMA_VERSION,
                catalog_version,
                status,
                json.dumps(payload, ensure_ascii=False),
                model,
                int(fallback_used),
                now,
                now,
            ),
        )
        self.connection.commit()
        record = self.get(processo_id)
        if record is None:
            raise RuntimeError("analise de teses salva nao pode ser carregada")
        return record


def _record_from_row(row: sqlite3.Row | None) -> DefenseThesesRecord | None:
    if row is None:
        return None
    payload = json.loads(str(row["payload_json"]))
    if not isinstance(payload, dict):
        raise ValueError("payload das teses defensivas deve ser um objeto")
    return DefenseThesesRecord(
        processo_id=str(row["processo_id"]),
        schema_version=str(row["schema_version"]),
        catalog_version=str(row["catalog_version"]),
        status=str(row["status"]),
        payload=payload,
        model=str(row["model"]),
        fallback_used=bool(row["fallback_used"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )
