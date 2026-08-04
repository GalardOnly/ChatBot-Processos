from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass

from preparador_audiencia.repositories import utc_now_text

COMPARISON_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class TestimonyComparisonRecord:
    id: str
    processo_id: str
    testimony_a_id: str
    testimony_b_id: str
    transcription_schema_version: str
    schema_version: str
    payload: dict[str, object]
    model: str
    fallback_used: bool
    created_at: str
    updated_at: str


class TestimonyComparisonRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def get(self, comparison_id: str) -> TestimonyComparisonRecord | None:
        row = self.connection.execute(
            "SELECT * FROM testimony_comparisons WHERE id = ?",
            (comparison_id,),
        ).fetchone()
        return _record_from_row(row)

    def get_for_pair(
        self,
        processo_id: str,
        testimony_a_id: str,
        testimony_b_id: str,
        transcription_schema_version: str,
    ) -> TestimonyComparisonRecord | None:
        comparison_id, _, _ = comparison_identity(
            processo_id,
            testimony_a_id,
            testimony_b_id,
            transcription_schema_version,
        )
        return self.get(comparison_id)

    def list_for_testimony(
        self,
        processo_id: str,
        testimony_id: str,
    ) -> list[TestimonyComparisonRecord]:
        rows = self.connection.execute(
            """
            SELECT *
            FROM testimony_comparisons
            WHERE processo_id = ?
              AND (testimony_a_id = ? OR testimony_b_id = ?)
            ORDER BY updated_at DESC, id
            """,
            (processo_id, testimony_id, testimony_id),
        ).fetchall()
        return [record for row in rows if (record := _record_from_row(row)) is not None]

    def save(
        self,
        processo_id: str,
        testimony_a_id: str,
        testimony_b_id: str,
        transcription_schema_version: str,
        *,
        payload: dict[str, object],
        model: str,
        fallback_used: bool,
    ) -> TestimonyComparisonRecord:
        comparison_id, canonical_a, canonical_b = comparison_identity(
            processo_id,
            testimony_a_id,
            testimony_b_id,
            transcription_schema_version,
        )
        now = utc_now_text()
        self.connection.execute(
            """
            INSERT INTO testimony_comparisons (
                id, processo_id, testimony_a_id, testimony_b_id,
                transcription_schema_version, schema_version, payload_json,
                model, fallback_used, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                payload_json = excluded.payload_json,
                model = excluded.model,
                fallback_used = excluded.fallback_used,
                updated_at = excluded.updated_at
            """,
            (
                comparison_id,
                processo_id,
                canonical_a,
                canonical_b,
                transcription_schema_version,
                COMPARISON_SCHEMA_VERSION,
                json.dumps(payload, ensure_ascii=False),
                model,
                int(fallback_used),
                now,
                now,
            ),
        )
        self.connection.commit()
        record = self.get(comparison_id)
        if record is None:
            raise RuntimeError("comparacao salva nao pode ser carregada")
        return record


def comparison_identity(
    processo_id: str,
    testimony_a_id: str,
    testimony_b_id: str,
    transcription_schema_version: str,
) -> tuple[str, str, str]:
    canonical_a, canonical_b = sorted((testimony_a_id, testimony_b_id))
    seed = "|".join(
        (
            processo_id,
            canonical_a,
            canonical_b,
            transcription_schema_version,
            COMPARISON_SCHEMA_VERSION,
        )
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"cmp-{digest}", canonical_a, canonical_b


def _record_from_row(row: sqlite3.Row | None) -> TestimonyComparisonRecord | None:
    if row is None:
        return None
    payload = json.loads(str(row["payload_json"]))
    if not isinstance(payload, dict):
        raise ValueError("payload da comparacao deve ser um objeto")
    return TestimonyComparisonRecord(
        id=str(row["id"]),
        processo_id=str(row["processo_id"]),
        testimony_a_id=str(row["testimony_a_id"]),
        testimony_b_id=str(row["testimony_b_id"]),
        transcription_schema_version=str(row["transcription_schema_version"]),
        schema_version=str(row["schema_version"]),
        payload=payload,
        model=str(row["model"]),
        fallback_used=bool(row["fallback_used"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )
