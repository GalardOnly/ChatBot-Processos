from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from preparador_audiencia.repositories import utc_now_text

NULLITY_ANALYSIS_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class NullityAnalysisRecord:
    processo_id: str
    topic_id: str
    schema_version: str
    catalog_version: str
    conclusion: str
    payload: dict[str, object]
    model: str
    fallback_used: bool
    search_mode: str
    created_at: str
    updated_at: str


class NullityAnalysisRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def get(self, processo_id: str, topic_id: str) -> NullityAnalysisRecord | None:
        row = self.connection.execute(
            """
            SELECT * FROM nullity_analyses
            WHERE processo_id = ? AND topic_id = ?
            """,
            (processo_id, topic_id),
        ).fetchone()
        return _record_from_row(row)

    def list_for_process(self, processo_id: str) -> list[NullityAnalysisRecord]:
        rows = self.connection.execute(
            """
            SELECT * FROM nullity_analyses
            WHERE processo_id = ?
            ORDER BY topic_id
            """,
            (processo_id,),
        ).fetchall()
        return [_record_from_row(row) for row in rows]

    def save(
        self,
        processo_id: str,
        topic_id: str,
        *,
        catalog_version: str,
        conclusion: str,
        payload: dict[str, object],
        model: str,
        fallback_used: bool,
        search_mode: str,
    ) -> NullityAnalysisRecord:
        now = utc_now_text()
        self.connection.execute(
            """
            INSERT INTO nullity_analyses (
                processo_id, topic_id, schema_version, catalog_version,
                conclusion, payload_json, model, fallback_used, search_mode,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(processo_id, topic_id) DO UPDATE SET
                schema_version = excluded.schema_version,
                catalog_version = excluded.catalog_version,
                conclusion = excluded.conclusion,
                payload_json = excluded.payload_json,
                model = excluded.model,
                fallback_used = excluded.fallback_used,
                search_mode = excluded.search_mode,
                updated_at = excluded.updated_at
            """,
            (
                processo_id,
                topic_id,
                NULLITY_ANALYSIS_SCHEMA_VERSION,
                catalog_version,
                conclusion,
                json.dumps(payload, ensure_ascii=False),
                model,
                int(fallback_used),
                search_mode,
                now,
                now,
            ),
        )
        self.connection.commit()
        record = self.get(processo_id, topic_id)
        if record is None:
            raise RuntimeError("analise de nulidade salva nao pode ser carregada")
        return record


def _record_from_row(row: sqlite3.Row | None) -> NullityAnalysisRecord | None:
    if row is None:
        return None
    payload = json.loads(str(row["payload_json"]))
    if not isinstance(payload, dict):
        raise ValueError("payload da analise de nulidade deve ser um objeto")
    return NullityAnalysisRecord(
        processo_id=str(row["processo_id"]),
        topic_id=str(row["topic_id"]),
        schema_version=str(row["schema_version"]),
        catalog_version=str(row["catalog_version"]),
        conclusion=str(row["conclusion"]),
        payload=payload,
        model=str(row["model"]),
        fallback_used=bool(row["fallback_used"]),
        search_mode=str(row["search_mode"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )
