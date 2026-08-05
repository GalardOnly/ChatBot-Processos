import sqlite3
from pathlib import Path

import pytest

from preparador_audiencia.chat import ChatResult
from preparador_audiencia.integrated_chat_benchmark import (
    build_chat_reference_suite,
    create_database_snapshot,
    estimate_chat_llm_calls,
    run_chat_observations,
)
from preparador_audiencia.reference_suite import load_reference_suite
from preparador_audiencia.search import SearchResult

DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
REFERENCE_SUITE_PATH = DATA_ROOT / "reference_suite_multidomain.json"
TEST_PROCESS_ID = "stj-resp-1876047-saude"


def _suite():
    return build_chat_reference_suite(
        load_reference_suite(REFERENCE_SUITE_PATH),
        test_process_ids={TEST_PROCESS_ID},
    )


def test_builds_public_chat_suite_without_document_leakage() -> None:
    suite = _suite()

    assert len(suite.cases) == 10
    development = {
        case.source.reference_id
        for case in suite.cases
        if case.split == "development"
    }
    test = {
        case.source.reference_id for case in suite.cases if case.split == "test"
    }
    assert development.isdisjoint(test)
    assert test == {TEST_PROCESS_ID}
    first_terms = suite.cases[0].expected.required_items
    assert "Recurso Especial || REsp" in first_terms
    assert "1.481.531" in first_terms
    assert 16 in suite.cases[0].expected.relevant_pages
    assert estimate_chat_llm_calls(3) == 6


def test_response_items_accept_declared_equivalent_wording(monkeypatch) -> None:
    suite = _suite()
    case = next(
        item
        for item in suite.cases
        if item.id.endswith("medidas-protetivas-aplicadas")
    )
    source = SearchResult(
        text="A decisao fixou distancia minima de 200m.",
        page_number=3,
        chunk_index=0,
        document_type="acordao",
        score=1.0,
    )

    monkeypatch.setattr(
        "preparador_audiencia.integrated_chat_benchmark._validate_process_map",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "preparador_audiencia.integrated_chat_benchmark.answer_process_question",
        lambda **_kwargs: ChatResult(
            pergunta=case.description,
            resposta=(
                "Em 29/05/2018 foram impostas proibicao de aproximacao e proibicao "
                "de contato, com distancia de 200 metros [p. 3]."
            ),
            modelo="gemini:test",
            fallback_usado=False,
            fontes=[source],
            latency_ms=10,
        ),
    )

    run = run_chat_observations(
        suite,
        process_map={case.source.reference_id: "proc-1"},
        split="development",
        case_ids={case.id},
        top_k=5,
        primary_model="gemini:test",
        fallback_model="groq:test",
        max_llm_calls=2,
        run_id="aliases-test",
    )

    assert "200m || 200 metros || duzentos metros" in run.observations[0].items


def test_budget_is_checked_before_process_mapping() -> None:
    suite = _suite()
    case_id = suite.cases[0].id

    with pytest.raises(ValueError, match="acima do limite"):
        run_chat_observations(
            suite,
            process_map={},
            split="development",
            case_ids={case_id},
            top_k=5,
            primary_model="gemini:test",
            fallback_model="groq:test",
            max_llm_calls=1,
            run_id="budget-test",
        )


def test_records_answer_model_sources_and_citations(monkeypatch) -> None:
    suite = _suite()
    case = suite.cases[0]
    expected_term = case.expected.required_items[0]
    source = SearchResult(
        text=f"Cabecalho com {expected_term} e identificacao do relator.",
        page_number=1,
        chunk_index=0,
        document_type="acordao",
        score=1.0,
    )

    def fake_answer(**_kwargs):
        return ChatResult(
            pergunta=case.description,
            resposta=f"O recurso e {expected_term} [p. 1].",
            modelo="gemini:test",
            fallback_usado=False,
            fontes=[source],
            latency_ms=20,
        )

    monkeypatch.setattr(
        "preparador_audiencia.integrated_chat_benchmark._validate_process_map",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "preparador_audiencia.integrated_chat_benchmark.answer_process_question",
        fake_answer,
    )

    run = run_chat_observations(
        suite,
        process_map={case.source.reference_id: "proc-1"},
        split="development",
        case_ids={case.id},
        top_k=5,
        primary_model="gemini:test",
        fallback_model="groq:test",
        max_llm_calls=2,
        run_id="answer-test",
    )

    observation = run.observations[0]
    assert observation.label == "resposta_gerada"
    assert observation.model == "gemini:test"
    assert observation.fallback_used is False
    assert observation.llm_calls == 1
    assert observation.source_pages == (1,)
    assert observation.cited_pages == (1,)
    assert expected_term in observation.items
    assert observation.sources[0].text == source.text


def test_database_snapshot_does_not_modify_source(tmp_path) -> None:
    source = tmp_path / "source.sqlite3"
    target = tmp_path / "snapshot.sqlite3"
    connection = sqlite3.connect(source)
    connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
    connection.execute("INSERT INTO sample VALUES ('original')")
    connection.commit()
    connection.close()

    snapshot = create_database_snapshot(source, target)
    copied = sqlite3.connect(snapshot)
    copied.execute("UPDATE sample SET value = 'alterado'")
    copied.commit()
    copied.close()

    original = sqlite3.connect(source)
    value = original.execute("SELECT value FROM sample").fetchone()[0]
    original.close()
    assert value == "original"
