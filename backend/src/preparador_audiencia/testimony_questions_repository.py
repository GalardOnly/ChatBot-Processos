from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass

from preparador_audiencia.repositories import utc_now_text
from preparador_audiencia.testimony_comparison_repository import (
    TestimonyComparisonRecord,
)

QUESTION_GUIDE_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class TestimonyQuestionGuideRecord:
    id: str
    processo_id: str
    testimony_id: str
    transcription_schema_version: str
    comparison_fingerprint: str
    schema_version: str
    payload: dict[str, object]
    model: str
    fallback_used: bool
    created_at: str
    updated_at: str


class TestimonyQuestionGuideRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def get(self, guide_id: str) -> TestimonyQuestionGuideRecord | None:
        row = self.connection.execute(
            "SELECT * FROM testimony_question_guides WHERE id = ?",
            (guide_id,),
        ).fetchone()
        return _record_from_row(row)

    def get_current(
        self,
        processo_id: str,
        testimony_id: str,
        transcription_schema_version: str,
        comparison_fingerprint: str,
    ) -> TestimonyQuestionGuideRecord | None:
        guide_id = question_guide_identity(
            processo_id,
            testimony_id,
            transcription_schema_version,
            comparison_fingerprint,
        )
        return self.get(guide_id)

    def save(
        self,
        processo_id: str,
        testimony_id: str,
        transcription_schema_version: str,
        comparison_fingerprint: str,
        *,
        payload: dict[str, object],
        model: str,
        fallback_used: bool,
    ) -> TestimonyQuestionGuideRecord:
        guide_id = question_guide_identity(
            processo_id,
            testimony_id,
            transcription_schema_version,
            comparison_fingerprint,
        )
        now = utc_now_text()
        self.connection.execute(
            """
            INSERT INTO testimony_question_guides (
                id, processo_id, testimony_id, transcription_schema_version,
                comparison_fingerprint, schema_version, payload_json, model,
                fallback_used, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                payload_json = excluded.payload_json,
                model = excluded.model,
                fallback_used = excluded.fallback_used,
                updated_at = excluded.updated_at
            """,
            (
                guide_id,
                processo_id,
                testimony_id,
                transcription_schema_version,
                comparison_fingerprint,
                QUESTION_GUIDE_SCHEMA_VERSION,
                json.dumps(payload, ensure_ascii=False),
                model,
                int(fallback_used),
                now,
                now,
            ),
        )
        self.connection.commit()
        record = self.get(guide_id)
        if record is None:
            raise RuntimeError("roteiro salvo nao pode ser carregado")
        return record


def comparison_fingerprint(comparisons: list[TestimonyComparisonRecord]) -> str:
    values = sorted(
        f"{item.id}:{item.updated_at}"
        for item in comparisons
    )
    if not values:
        return "sem-comparacoes"
    return hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()[:16]


def question_guide_identity(
    processo_id: str,
    testimony_id: str,
    transcription_schema_version: str,
    comparison_fingerprint_value: str,
) -> str:
    seed = "|".join(
        (
            processo_id,
            testimony_id,
            transcription_schema_version,
            comparison_fingerprint_value,
            QUESTION_GUIDE_SCHEMA_VERSION,
        )
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"rot-{digest}"


def _record_from_row(row: sqlite3.Row | None) -> TestimonyQuestionGuideRecord | None:
    if row is None:
        return None
    payload = json.loads(str(row["payload_json"]))
    if not isinstance(payload, dict):
        raise ValueError("payload do roteiro deve ser um objeto")
    return TestimonyQuestionGuideRecord(
        id=str(row["id"]),
        processo_id=str(row["processo_id"]),
        testimony_id=str(row["testimony_id"]),
        transcription_schema_version=str(row["transcription_schema_version"]),
        comparison_fingerprint=str(row["comparison_fingerprint"]),
        schema_version=str(row["schema_version"]),
        payload=payload,
        model=str(row["model"]),
        fallback_used=bool(row["fallback_used"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )
