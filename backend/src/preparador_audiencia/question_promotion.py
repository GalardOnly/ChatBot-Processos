from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from preparador_audiencia.question_bank import (
    DEFAULT_APPROVED_QUESTION_PATH,
    QuestionTemplate,
    load_approved_question_templates,
    write_approved_question_templates,
)
from preparador_audiencia.question_sources import QuestionCandidate

REVIEW_VERSION = "0.1"


@dataclass(frozen=True)
class QuestionReviewItem:
    candidate_id: str
    decision: str
    notes: str
    source_id: str
    source_title: str
    source_url: str
    approved_template: QuestionTemplate

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["approved_template"] = self.approved_template.to_dict()
        return payload


@dataclass(frozen=True)
class PromotionResult:
    approved_path: str
    promoted_count: int
    skipped_count: int
    total_approved_templates: int


def build_review_items(candidates: list[QuestionCandidate]) -> list[QuestionReviewItem]:
    return [
        QuestionReviewItem(
            candidate_id=candidate.id,
            decision="pending",
            notes="",
            source_id=candidate.source_id,
            source_title=candidate.source_title,
            source_url=candidate.source_url,
            approved_template=_candidate_to_template(candidate),
        )
        for candidate in candidates
    ]


def write_review_file(
    candidates: list[QuestionCandidate],
    output_path: str | Path,
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": REVIEW_VERSION,
                "instructions": (
                    "Altere decision para approved nas perguntas que devem entrar no banco "
                    "oficial. Ajuste approved_template se quiser melhorar titulo, pergunta, "
                    "tags ou prioridade antes da promocao."
                ),
                "items": [item.to_dict() for item in build_review_items(candidates)],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def promote_review_file(
    review_path: str | Path,
    *,
    approved_path: str | Path | None = None,
) -> PromotionResult:
    target_path = (
        Path(approved_path) if approved_path is not None else DEFAULT_APPROVED_QUESTION_PATH
    )
    review_items = load_review_items(review_path)
    current = {template.id: template for template in load_approved_question_templates(target_path)}
    promoted = 0
    skipped = 0

    for item in review_items:
        if item.decision != "approved":
            skipped += 1
            continue
        current[item.approved_template.id] = item.approved_template
        promoted += 1

    approved_templates = sorted(
        current.values(),
        key=lambda item: (item.prioridade, item.area, item.id),
    )
    write_approved_question_templates(approved_templates, target_path)
    return PromotionResult(
        approved_path=str(target_path),
        promoted_count=promoted,
        skipped_count=skipped,
        total_approved_templates=len(approved_templates),
    )


def load_review_items(path: str | Path) -> list[QuestionReviewItem]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [_review_item_from_dict(item) for item in payload.get("items", [])]


def _candidate_to_template(candidate: QuestionCandidate) -> QuestionTemplate:
    return QuestionTemplate(
        id=_approved_id(candidate.id),
        titulo=candidate.titulo,
        area=candidate.area,
        audiencia=candidate.audiencia,
        objetivo=candidate.objetivo,
        pergunta=candidate.pergunta,
        quando_usar=candidate.quando_usar,
        tags=sorted(set(candidate.tags + ["promovida", candidate.source_kind])),
        prioridade=max(1, candidate.prioridade),
    )


def _approved_id(candidate_id: str) -> str:
    return candidate_id.replace("cand_", "aprovada_", 1)


def _review_item_from_dict(item: dict[str, object]) -> QuestionReviewItem:
    template_payload = item["approved_template"]
    if not isinstance(template_payload, dict):
        raise ValueError("approved_template deve ser um objeto")
    return QuestionReviewItem(
        candidate_id=str(item["candidate_id"]),
        decision=str(item.get("decision", "pending")),
        notes=str(item.get("notes", "")),
        source_id=str(item["source_id"]),
        source_title=str(item["source_title"]),
        source_url=str(item["source_url"]),
        approved_template=QuestionTemplate(
            id=str(template_payload["id"]),
            titulo=str(template_payload["titulo"]),
            area=str(template_payload["area"]),
            audiencia=str(template_payload["audiencia"]),
            objetivo=str(template_payload["objetivo"]),
            pergunta=str(template_payload["pergunta"]),
            quando_usar=str(template_payload["quando_usar"]),
            tags=[str(tag) for tag in template_payload.get("tags", [])],
            prioridade=int(template_payload["prioridade"]),
        ),
    )
