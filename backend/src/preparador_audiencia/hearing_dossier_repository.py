from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from preparador_audiencia.repositories import utc_now_text

DOSSIER_SCHEMA_VERSION = "0.2"
DOSSIER_SECTION_KEYS = (
    "marcos_essenciais",
    "depoimentos",
    "contradicoes",
)


@dataclass(frozen=True)
class HearingDossierSectionRecord:
    key: str
    status: str
    payload: dict[str, object]
    model: str | None
    fallback_used: bool
    retrieval_ms: int | None
    generation_ms: int | None
    error_message: str | None
    updated_at: str


@dataclass(frozen=True)
class HearingDossierRecord:
    processo_id: str
    schema_version: str
    status: str
    error_message: str | None
    created_at: str
    updated_at: str
    sections: tuple[HearingDossierSectionRecord, ...]


class HearingDossierRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def get(self, processo_id: str) -> HearingDossierRecord | None:
        row = self.connection.execute(
            "SELECT * FROM hearing_dossiers WHERE processo_id = ?",
            (processo_id,),
        ).fetchone()
        if row is None:
            return None
        section_rows = self.connection.execute(
            """
            SELECT *
            FROM hearing_dossier_sections
            WHERE processo_id = ?
            ORDER BY id
            """,
            (processo_id,),
        ).fetchall()
        return HearingDossierRecord(
            processo_id=str(row["processo_id"]),
            schema_version=str(row["schema_version"]),
            status=str(row["status"]),
            error_message=row["error_message"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            sections=tuple(_section_from_row(item) for item in section_rows),
        )

    def prepare(
        self,
        processo_id: str,
        *,
        regenerate: bool = False,
    ) -> HearingDossierRecord:
        current = self.get(processo_id)
        should_reset = regenerate or (
            current is not None and current.schema_version != DOSSIER_SCHEMA_VERSION
        )
        if current is None:
            self._create(processo_id)
        elif should_reset:
            self._reset(processo_id)
        prepared = self.get(processo_id)
        if prepared is None:
            raise RuntimeError("dossie criado nao pode ser carregado")
        return prepared

    def mark_processing(self, processo_id: str) -> None:
        self.connection.execute(
            """
            UPDATE hearing_dossiers
            SET status = 'processando', error_message = NULL, updated_at = ?
            WHERE processo_id = ?
            """,
            (utc_now_text(), processo_id),
        )
        self.connection.commit()

    def mark_section_processing(self, processo_id: str, section_key: str) -> None:
        _validate_section_key(section_key)
        now = utc_now_text()
        self.connection.execute(
            """
            UPDATE hearing_dossier_sections
            SET status = 'processando', error_message = NULL, updated_at = ?
            WHERE processo_id = ? AND section_key = ?
            """,
            (now, processo_id, section_key),
        )
        self.connection.execute(
            """
            UPDATE hearing_dossiers
            SET status = 'processando', error_message = NULL, updated_at = ?
            WHERE processo_id = ?
            """,
            (now, processo_id),
        )
        self.connection.commit()

    def save_section(
        self,
        processo_id: str,
        section_key: str,
        payload: dict[str, object],
        *,
        model: str | None,
        fallback_used: bool,
        retrieval_ms: int | None = None,
        generation_ms: int | None = None,
    ) -> None:
        _validate_section_key(section_key)
        now = utc_now_text()
        self.connection.execute(
            """
            UPDATE hearing_dossier_sections
            SET status = 'concluido', payload_json = ?, model = ?,
                fallback_used = ?, retrieval_ms = ?, generation_ms = ?,
                error_message = NULL, updated_at = ?
            WHERE processo_id = ? AND section_key = ?
            """,
            (
                json.dumps(payload, ensure_ascii=False),
                model,
                int(fallback_used),
                retrieval_ms,
                generation_ms,
                now,
                processo_id,
                section_key,
            ),
        )
        self.connection.execute(
            "UPDATE hearing_dossiers SET updated_at = ? WHERE processo_id = ?",
            (now, processo_id),
        )
        self.connection.commit()

    def mark_section_error(
        self,
        processo_id: str,
        section_key: str,
        error_message: str,
        *,
        retrieval_ms: int | None = None,
        generation_ms: int | None = None,
    ) -> None:
        _validate_section_key(section_key)
        now = utc_now_text()
        self.connection.execute(
            """
            UPDATE hearing_dossier_sections
            SET status = 'erro', error_message = ?, retrieval_ms = ?,
                generation_ms = ?, updated_at = ?
            WHERE processo_id = ? AND section_key = ?
            """,
            (
                error_message,
                retrieval_ms,
                generation_ms,
                now,
                processo_id,
                section_key,
            ),
        )
        self.connection.execute(
            "UPDATE hearing_dossiers SET updated_at = ? WHERE processo_id = ?",
            (now, processo_id),
        )
        self.connection.commit()

    def finish(self, processo_id: str) -> HearingDossierRecord:
        rows = self.connection.execute(
            """
            SELECT status, error_message
            FROM hearing_dossier_sections
            WHERE processo_id = ?
            """,
            (processo_id,),
        ).fetchall()
        completed = sum(row["status"] == "concluido" for row in rows)
        if completed == len(DOSSIER_SECTION_KEYS):
            status = "concluido"
            error_message = None
        elif completed > 0:
            status = "parcial"
            error_message = "Uma ou mais secoes precisam ser tentadas novamente."
        else:
            status = "erro"
            errors = [str(row["error_message"]) for row in rows if row["error_message"]]
            error_message = errors[0] if errors else "Nenhuma secao pode ser concluida."
        self.connection.execute(
            """
            UPDATE hearing_dossiers
            SET status = ?, error_message = ?, updated_at = ?
            WHERE processo_id = ?
            """,
            (status, error_message, utc_now_text(), processo_id),
        )
        self.connection.commit()
        result = self.get(processo_id)
        if result is None:
            raise RuntimeError("dossie finalizado nao pode ser carregado")
        return result

    def _create(self, processo_id: str) -> None:
        now = utc_now_text()
        self.connection.execute(
            """
            INSERT INTO hearing_dossiers (
                processo_id, schema_version, status, error_message, created_at, updated_at
            )
            VALUES (?, ?, 'pendente', NULL, ?, ?)
            """,
            (processo_id, DOSSIER_SCHEMA_VERSION, now, now),
        )
        self.connection.executemany(
            """
            INSERT INTO hearing_dossier_sections (
                processo_id, section_key, status, payload_json, model,
                fallback_used, error_message, created_at, updated_at
            )
            VALUES (?, ?, 'pendente', NULL, NULL, 0, NULL, ?, ?)
            """,
            [(processo_id, key, now, now) for key in DOSSIER_SECTION_KEYS],
        )
        self.connection.commit()

    def _reset(self, processo_id: str) -> None:
        now = utc_now_text()
        self.connection.execute(
            "DELETE FROM hearing_dossier_sections WHERE processo_id = ?",
            (processo_id,),
        )
        self.connection.execute(
            """
            UPDATE hearing_dossiers
            SET schema_version = ?, status = 'pendente', error_message = NULL,
                updated_at = ?
            WHERE processo_id = ?
            """,
            (DOSSIER_SCHEMA_VERSION, now, processo_id),
        )
        self.connection.executemany(
            """
            INSERT INTO hearing_dossier_sections (
                processo_id, section_key, status, payload_json, model,
                fallback_used, error_message, created_at, updated_at
            )
            VALUES (?, ?, 'pendente', NULL, NULL, 0, NULL, ?, ?)
            """,
            [(processo_id, key, now, now) for key in DOSSIER_SECTION_KEYS],
        )
        self.connection.commit()


def _section_from_row(row: sqlite3.Row) -> HearingDossierSectionRecord:
    return HearingDossierSectionRecord(
        key=str(row["section_key"]),
        status=str(row["status"]),
        payload=json.loads(row["payload_json"] or "{}"),
        model=row["model"],
        fallback_used=bool(row["fallback_used"]),
        retrieval_ms=row["retrieval_ms"],
        generation_ms=row["generation_ms"],
        error_message=row["error_message"],
        updated_at=str(row["updated_at"]),
    )


def _validate_section_key(section_key: str) -> None:
    if section_key not in DOSSIER_SECTION_KEYS:
        raise ValueError(f"Secao desconhecida: {section_key}")
