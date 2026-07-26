import json

from preparador_audiencia.question_bank import list_question_templates
from preparador_audiencia.question_promotion import (
    build_review_items,
    promote_review_file,
    write_review_file,
)
from preparador_audiencia.question_sources import (
    generate_question_candidates,
    load_question_sources,
)


def test_build_review_items_starts_pending() -> None:
    candidates = generate_question_candidates(load_question_sources(), area="familia", limit=1)

    items = build_review_items(candidates)

    assert items[0].decision == "pending"
    assert items[0].approved_template.id.startswith("aprovada_")
    assert "promovida" in items[0].approved_template.tags


def test_promote_review_file_writes_approved_templates(tmp_path) -> None:
    review_path = tmp_path / "review.json"
    approved_path = tmp_path / "approved.json"
    candidates = generate_question_candidates(load_question_sources(), area="familia", limit=2)
    write_review_file(candidates, review_path)

    review_payload = json.loads(review_path.read_text(encoding="utf-8"))
    review_payload["items"][0]["decision"] = "approved"
    review_path.write_text(json.dumps(review_payload, ensure_ascii=False), encoding="utf-8")

    result = promote_review_file(review_path, approved_path=approved_path)
    templates = list_question_templates(approved_path=approved_path)

    assert result.promoted_count == 1
    assert result.skipped_count == 1
    assert result.total_approved_templates == 1
    approved_id = review_payload["items"][0]["approved_template"]["id"]
    assert any(template.id == approved_id for template in templates)


def test_promote_review_file_updates_existing_template(tmp_path) -> None:
    review_path = tmp_path / "review.json"
    approved_path = tmp_path / "approved.json"
    candidates = generate_question_candidates(load_question_sources(), area="familia", limit=1)
    write_review_file(candidates, review_path)

    review_payload = json.loads(review_path.read_text(encoding="utf-8"))
    review_payload["items"][0]["decision"] = "approved"
    review_payload["items"][0]["approved_template"]["titulo"] = "Titulo revisado"
    review_path.write_text(json.dumps(review_payload, ensure_ascii=False), encoding="utf-8")
    promote_review_file(review_path, approved_path=approved_path)

    review_payload["items"][0]["approved_template"]["titulo"] = "Titulo revisado de novo"
    review_path.write_text(json.dumps(review_payload, ensure_ascii=False), encoding="utf-8")
    result = promote_review_file(review_path, approved_path=approved_path)
    approved_payload = json.loads(approved_path.read_text(encoding="utf-8"))

    assert result.total_approved_templates == 1
    assert approved_payload["templates"][0]["titulo"] == "Titulo revisado de novo"
