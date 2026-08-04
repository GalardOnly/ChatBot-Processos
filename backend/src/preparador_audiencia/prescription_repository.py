from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass

from preparador_audiencia.prescription import (
    LEGAL_RULESET_VERSION,
    PRESCRIPTION_CALCULATION_VERSION,
)
from preparador_audiencia.repositories import utc_now_text


@dataclass(frozen=True)
class PrescriptionCalculationRecord:
    id: str
    processo_id: str
    schema_version: str
    legal_ruleset_version: str
    input_payload: dict[str, object]
    result_payload: dict[str, object]
    created_at: str
    updated_at: str


class PrescriptionCalculationRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def get(self, calculation_id: str) -> PrescriptionCalculationRecord | None:
        row = self.connection.execute(
            "SELECT * FROM prescription_calculations WHERE id = ?",
            (calculation_id,),
        ).fetchone()
        return _record_from_row(row)

    def save(
        self,
        processo_id: str,
        *,
        input_payload: dict[str, object],
        result_payload: dict[str, object],
    ) -> PrescriptionCalculationRecord:
        calculation_id = prescription_calculation_identity(processo_id, input_payload)
        now = utc_now_text()
        self.connection.execute(
            """
            INSERT INTO prescription_calculations (
                id, processo_id, schema_version, legal_ruleset_version,
                input_json, result_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                result_json = excluded.result_json,
                updated_at = excluded.updated_at
            """,
            (
                calculation_id,
                processo_id,
                PRESCRIPTION_CALCULATION_VERSION,
                LEGAL_RULESET_VERSION,
                json.dumps(input_payload, ensure_ascii=False, sort_keys=True),
                json.dumps(result_payload, ensure_ascii=False, sort_keys=True),
                now,
                now,
            ),
        )
        self.connection.commit()
        record = self.get(calculation_id)
        if record is None:
            raise RuntimeError("calculo de prescricao salvo nao pode ser carregado")
        return record


def prescription_calculation_identity(
    processo_id: str,
    input_payload: dict[str, object],
) -> str:
    canonical = json.dumps(
        input_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    seed = "|".join(
        (
            processo_id,
            PRESCRIPTION_CALCULATION_VERSION,
            LEGAL_RULESET_VERSION,
            canonical,
        )
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"presc-{digest}"


def _record_from_row(row: sqlite3.Row | None) -> PrescriptionCalculationRecord | None:
    if row is None:
        return None
    input_payload = json.loads(str(row["input_json"]))
    result_payload = json.loads(str(row["result_json"]))
    if not isinstance(input_payload, dict) or not isinstance(result_payload, dict):
        raise ValueError("payload do calculo de prescricao deve ser um objeto")
    return PrescriptionCalculationRecord(
        id=str(row["id"]),
        processo_id=str(row["processo_id"]),
        schema_version=str(row["schema_version"]),
        legal_ruleset_version=str(row["legal_ruleset_version"]),
        input_payload=input_payload,
        result_payload=result_payload,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )
