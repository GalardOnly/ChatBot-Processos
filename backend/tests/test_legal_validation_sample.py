import json
from pathlib import Path

import fitz
import pytest

from preparador_audiencia.legal_validation_sample import (
    STATUS_APPROVED,
    STATUS_BLOCKED,
    STATUS_HUMAN_REVIEW,
    STATUS_VISUAL_REVIEW,
    approve_anonymized_candidate,
    create_legal_review_worksheet,
    finalize_legal_review_worksheet,
    load_validation_sample_config,
    prepare_anonymized_candidate,
    verify_anonymized_candidate,
)
from preparador_audiencia.reference_suite import load_reference_suite

PERSON_NAME = "JOAO DA SILVA"
PERSON_CPF = "123.456.789-00"
PERSON_EMAIL = "joao@example.com"
PROCESS_NUMBER = "0001234-56.2024.8.14.0301"


def _write_config(tmp_path: Path, *, confirmed: bool = True) -> Path:
    path = tmp_path / "amostra.anonimizacao.local.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "case_id": "criminal-001",
                "domain": "penal.instrucao",
                "authorization": {
                    "confirmed": confirmed,
                    "reference": "autorizacao-interna-001",
                },
                "aliases": [
                    {
                        "id": "reu-01",
                        "replacement": "PESSOA A",
                        "values": [PERSON_NAME],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_pdf(tmp_path: Path, *, with_image: bool = False) -> Path:
    path = tmp_path / "original.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text(
        (40, 60),
        (
            f"Reu: {PERSON_NAME}\nCPF: {PERSON_CPF}\n"
            f"Email: {PERSON_EMAIL}\nProcesso: {PROCESS_NUMBER}\n"
            "A audiencia confirmou a oitiva da testemunha."
        ),
        fontsize=10,
    )
    if with_image:
        pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 20, 20), False)
        pixmap.clear_with(220)
        page.insert_image(fitz.Rect(40, 150, 100, 210), pixmap=pixmap)
    document.set_metadata({"title": PERSON_NAME, "author": PERSON_EMAIL})
    document.save(path)
    document.close()
    return path


def _prepare(tmp_path: Path, *, with_image: bool = False) -> tuple[Path, Path]:
    config = _write_config(tmp_path)
    source = _write_pdf(tmp_path, with_image=with_image)
    manifest = prepare_anonymized_candidate(
        source,
        config,
        tmp_path / "samples",
    )
    return manifest, config


def _candidate_path(manifest_path: Path) -> Path:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return manifest_path.parent / manifest["candidate_document"]


def _approve(manifest: Path, *, images_reviewed: bool = False) -> None:
    approve_anonymized_candidate(
        manifest,
        reviewer="revisor-anonimizacao-01",
        authorization_confirmed=True,
        all_pages_reviewed=True,
        images_reviewed=images_reviewed,
    )


def test_prepares_candidate_without_leaking_original_values(tmp_path) -> None:
    manifest_path, _config = _prepare(tmp_path)
    manifest_text = manifest_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    candidate = _candidate_path(manifest_path)

    with fitz.open(candidate) as document:
        candidate_text = "\n".join(page.get_text("text") for page in document)
        assert document.metadata["title"] == ""
        assert document.metadata["author"] == ""

    assert manifest["status"] == STATUS_HUMAN_REVIEW
    assert PERSON_NAME not in candidate_text
    assert PERSON_CPF not in candidate_text
    assert PERSON_EMAIL not in candidate_text
    assert PROCESS_NUMBER not in candidate_text
    assert "PESSOA A" in candidate_text
    assert PERSON_NAME not in manifest_text
    assert PERSON_CPF not in manifest_text
    assert PERSON_EMAIL not in manifest_text
    assert PROCESS_NUMBER not in manifest_text
    assert manifest["residual_identifiers"] == []
    assert {item["category"] for item in manifest["detected_identifiers"]} >= {
        "cpf",
        "email",
        "numero_processo",
    }


def test_rejects_sample_without_confirmed_authorization(tmp_path) -> None:
    config = _write_config(tmp_path, confirmed=False)

    with pytest.raises(ValueError, match="autorizacao precisa estar confirmada"):
        load_validation_sample_config(config)


def test_requires_visual_review_for_pages_with_images(tmp_path) -> None:
    manifest_path, _config = _prepare(tmp_path, with_image=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["status"] == STATUS_VISUAL_REVIEW
    assert manifest["visual_review_pages"] == [1]
    with pytest.raises(ValueError, match="imagens precisam de revisao visual"):
        _approve(manifest_path, images_reviewed=False)

    _approve(manifest_path, images_reviewed=True)
    approved = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert approved["status"] == STATUS_APPROVED


def test_verification_blocks_identifier_reintroduced_by_manual_edit(tmp_path) -> None:
    manifest_path, config = _prepare(tmp_path)
    candidate = _candidate_path(manifest_path)
    edited = candidate.with_name("edited.pdf")
    with fitz.open(candidate) as document:
        document[0].insert_text((40, 250), "Contato: 1198765-4321", fontsize=10)
        document.save(edited)
    edited.replace(candidate)

    manifest = verify_anonymized_candidate(manifest_path, config)

    assert manifest["status"] == STATUS_BLOCKED
    assert any(
        item["category"] == "telefone"
        for item in manifest["residual_identifiers"]
    )
    with pytest.raises(ValueError, match="ainda possui residuos"):
        _approve(manifest_path)


def test_approval_rejects_candidate_changed_after_verification(tmp_path) -> None:
    manifest_path, _config = _prepare(tmp_path)
    candidate = _candidate_path(manifest_path)
    candidate.write_bytes(candidate.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="execute verificar novamente"):
        _approve(manifest_path)


def test_creates_worksheet_only_after_anonymization_approval(tmp_path) -> None:
    manifest_path, _config = _prepare(tmp_path)

    with pytest.raises(ValueError, match="anonimizacao precisa estar aprovada"):
        create_legal_review_worksheet(manifest_path)

    _approve(manifest_path)
    worksheet = create_legal_review_worksheet(manifest_path)
    payload = json.loads(worksheet.read_text(encoding="utf-8"))

    assert payload["minimum_reviewers"] == 2
    assert len(payload["questions"]) == 12
    assert all(question["include_in_benchmark"] for question in payload["questions"])
    assert all(question["reviews"] == [] for question in payload["questions"])


def test_finalizes_reviewed_worksheet_as_reference_suite(tmp_path) -> None:
    manifest_path, config = _prepare(tmp_path)
    _approve(manifest_path)
    worksheet = create_legal_review_worksheet(manifest_path)
    payload = json.loads(worksheet.read_text(encoding="utf-8"))
    for question in payload["questions"]:
        question["expected_pages"] = [1]
        question["expected_terms"] = ["audiencia", "testemunha"]
        question["response_relevant_pages"] = [1]
        question["response_expected_terms"] = ["audiencia", "testemunha"]
        question["reviews"] = [
            {
                "reviewer": "defensor-01",
                "decision": "approved",
                "notes": "Conferido na pagina indicada.",
            },
            {
                "reviewer": "defensor-02",
                "decision": "approved",
                "notes": "Revisao independente concluida.",
            },
        ]
    worksheet.write_text(json.dumps(payload), encoding="utf-8")

    suite_path = finalize_legal_review_worksheet(worksheet, config)
    suite = load_reference_suite(suite_path)

    assert len(suite.processes) == 1
    assert len(suite.processes[0].cases) == 12
    assert all(case.review_status == "approved" for case in suite.processes[0].cases)
    assert all("defensor-01" in case.reviewer for case in suite.processes[0].cases)
    updated = json.loads(worksheet.read_text(encoding="utf-8"))
    assert updated["status"] == "approved"


def test_finalization_requires_two_independent_reviewers(tmp_path) -> None:
    manifest_path, config = _prepare(tmp_path)
    _approve(manifest_path)
    worksheet = create_legal_review_worksheet(manifest_path)
    payload = json.loads(worksheet.read_text(encoding="utf-8"))
    for question in payload["questions"]:
        question["expected_pages"] = [1]
        question["expected_terms"] = ["audiencia"]
        question["response_relevant_pages"] = [1]
        question["response_expected_terms"] = ["audiencia"]
        question["reviews"] = [
            {
                "reviewer": "defensor-01",
                "decision": "approved",
                "notes": "Conferido.",
            }
        ]
    worksheet.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="dois revisores|2 revisores"):
        finalize_legal_review_worksheet(worksheet, config)


def test_finalization_blocks_original_alias_reintroduced_in_worksheet(tmp_path) -> None:
    manifest_path, config = _prepare(tmp_path)
    _approve(manifest_path)
    worksheet = create_legal_review_worksheet(manifest_path)
    payload = json.loads(worksheet.read_text(encoding="utf-8"))
    for question in payload["questions"]:
        question["expected_pages"] = [1]
        question["expected_terms"] = ["audiencia"]
        question["response_relevant_pages"] = [1]
        question["response_expected_terms"] = ["testemunha"]
        question["reviews"] = [
            {
                "reviewer": "defensor-01",
                "decision": "approved",
                "notes": "Conferido.",
            },
            {
                "reviewer": "defensor-02",
                "decision": "approved",
                "notes": "Revisao independente concluida.",
            },
        ]
    payload["questions"][0]["expected_terms"] = [PERSON_NAME]
    worksheet.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="aliases originais"):
        finalize_legal_review_worksheet(worksheet, config)


def test_finalization_blocks_page_outside_candidate_pdf(tmp_path) -> None:
    manifest_path, config = _prepare(tmp_path)
    _approve(manifest_path)
    worksheet = create_legal_review_worksheet(manifest_path)
    payload = json.loads(worksheet.read_text(encoding="utf-8"))
    for question in payload["questions"]:
        question["expected_pages"] = [1]
        question["expected_terms"] = ["audiencia"]
        question["response_relevant_pages"] = [1]
        question["response_expected_terms"] = ["testemunha"]
        question["reviews"] = [
            {
                "reviewer": "defensor-01",
                "decision": "approved",
                "notes": "Conferido.",
            },
            {
                "reviewer": "defensor-02",
                "decision": "approved",
                "notes": "Revisao independente concluida.",
            },
        ]
    payload["questions"][0]["expected_pages"] = [2]
    worksheet.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="pagina inexistente"):
        finalize_legal_review_worksheet(worksheet, config)


def test_finalization_allows_reviewed_question_exclusion(tmp_path) -> None:
    manifest_path, config = _prepare(tmp_path)
    _approve(manifest_path)
    worksheet = create_legal_review_worksheet(manifest_path)
    payload = json.loads(worksheet.read_text(encoding="utf-8"))
    for question in payload["questions"]:
        question["expected_pages"] = [1]
        question["expected_terms"] = ["audiencia"]
        question["response_relevant_pages"] = [1]
        question["response_expected_terms"] = ["testemunha"]
        question["reviews"] = [
            {
                "reviewer": "defensor-01",
                "decision": "approved",
                "notes": "Conferido.",
            },
            {
                "reviewer": "defensor-02",
                "decision": "approved",
                "notes": "Revisao independente concluida.",
            },
        ]
    excluded = payload["questions"][0]
    excluded["include_in_benchmark"] = False
    excluded["exclusion_reason"] = "Informacao ausente neste processo."
    excluded["expected_pages"] = []
    excluded["expected_terms"] = []
    excluded["response_relevant_pages"] = []
    excluded["response_expected_terms"] = []
    worksheet.write_text(json.dumps(payload), encoding="utf-8")

    suite_path = finalize_legal_review_worksheet(worksheet, config)
    suite = load_reference_suite(suite_path)

    assert len(suite.processes[0].cases) == 11
    assert all(case.id != excluded["id"] for case in suite.processes[0].cases)
