from dataclasses import replace
from pathlib import Path

import pytest

from preparador_audiencia.integrated_benchmark import (
    CaseObservation,
    ObservationRun,
    ObservationSource,
    load_integrated_benchmark_suite,
    load_observation_run,
    render_integrated_benchmark_markdown,
    run_integrated_benchmark,
)

DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
SUITE_PATH = DATA_ROOT / "integrated_benchmark_v01.json"
OBSERVATIONS_PATH = DATA_ROOT / "integrated_benchmark_observations_calibration.json"


def _loaded():
    return (
        load_integrated_benchmark_suite(SUITE_PATH),
        load_observation_run(OBSERVATIONS_PATH),
    )


def test_loads_versioned_suite_with_separate_splits() -> None:
    suite, observations = _loaded()

    assert suite.id == "preparador-audiencia-integrado-v0.1"
    assert len(suite.cases) == 12
    assert sum(case.split == "development" for case in suite.cases) == 6
    assert sum(case.split == "test" for case in suite.cases) == 6
    assert all(case.provenance == "synthetic" for case in suite.cases)
    assert all(case.review_status == "technical_review" for case in suite.cases)
    assert len(observations.observations) == 12


def test_calibration_scores_metrics_but_does_not_approve_legal_gate() -> None:
    suite, observations = _loaded()

    report = run_integrated_benchmark(suite, observations, split="development")

    assert report.cases_count == 6
    assert report.legal_approved_cases == 0
    assert report.gate_status == "not_eligible"
    assert all(engine.gate_status == "not_eligible" for engine in report.engines)
    chat = next(engine for engine in report.engines if engine.engine == "chat")
    assert chat.metrics.label_accuracy == 1.0
    assert chat.metrics.page_recall == 1.0
    assert chat.metrics.page_hit_rate == 1.0
    assert chat.metrics.citation_fidelity == 1.0
    assert chat.metrics.total_llm_calls == 1


def test_approved_test_case_can_pass_engine_gate() -> None:
    suite, observations = _loaded()
    original = next(case for case in suite.cases if case.id == "test-tese-autoria")
    approved = replace(original, review_status="legal_approved")
    controlled_suite = replace(suite, cases=(approved,))
    observation = next(
        item for item in observations.observations if item.case_id == approved.id
    )
    controlled_run = replace(observations, observations=(observation,))

    report = run_integrated_benchmark(
        controlled_suite,
        controlled_run,
        split="test",
    )

    assert report.gate_status == "passed"
    assert report.legal_approved_cases == 1
    assert report.engines[0].gate_status == "passed"
    assert report.engines[0].gate_metrics is not None


def test_false_positive_blocks_approved_engine_gate() -> None:
    suite, observations = _loaded()
    original = next(case for case in suite.cases if case.id == "test-tese-autoria")
    approved = replace(original, review_status="legal_approved")
    controlled_suite = replace(suite, cases=(approved,))
    observation = next(
        item for item in observations.observations if item.case_id == approved.id
    )
    unsafe = replace(observation, items=(*observation.items, "tese_sem_fonte"))
    unsafe_run = replace(observations, observations=(unsafe,))

    report = run_integrated_benchmark(controlled_suite, unsafe_run, split="test")

    assert report.gate_status == "failed"
    engine = report.engines[0]
    assert engine.metrics.false_positive_case_rate == 1.0
    assert any("false_positive_case_rate" in item for item in engine.failed_checks)


def test_missing_observation_is_reported_as_error() -> None:
    suite, observations = _loaded()
    empty_run = ObservationRun(
        suite_id=observations.suite_id,
        run_id="sem-observacoes",
        producer="test",
        generated_at=observations.generated_at,
        observations=(),
    )

    report = run_integrated_benchmark(
        suite,
        empty_run,
        split="development",
        case_ids={"dev-prescricao-esgotada"},
    )

    result = report.engines[0].cases[0]
    assert result.error == "observacao ausente"
    assert report.engines[0].metrics.error_rate == 1.0


def test_rejects_observations_from_unknown_case() -> None:
    suite, observations = _loaded()
    unknown = replace(observations.observations[0], case_id="caso-inexistente")
    invalid_run = replace(observations, observations=(unknown,))

    with pytest.raises(ValueError, match="Observacoes desconhecidas"):
        run_integrated_benchmark(suite, invalid_run)


def test_markdown_explains_calibration_limit() -> None:
    suite, observations = _loaded()
    report = run_integrated_benchmark(suite, observations)

    markdown = render_integrated_benchmark_markdown(report)

    assert "nao aprova a qualidade juridica" in markdown
    assert "calibration_fixture" in markdown


def test_report_preserves_detailed_chat_evidence() -> None:
    suite, observations = _loaded()
    original = next(
        item for item in observations.observations if item.case_id == "dev-chat-pessoas"
    )
    detailed = CaseObservation(
        **{
            **original.__dict__,
            "model": "gemini:test",
            "fallback_used": False,
            "response": "Resposta controlada [p. 27].",
            "sources": (ObservationSource(27, 0, "Trecho controlado da fonte."),),
        }
    )
    run = replace(
        observations,
        observations=tuple(
            detailed if item.case_id == detailed.case_id else item
            for item in observations.observations
        ),
    )

    report = run_integrated_benchmark(suite, run)
    markdown = render_integrated_benchmark_markdown(report)

    assert "Resposta controlada [p. 27]." in markdown
    assert "gemini:test" in markdown
    assert "Trecho controlado da fonte." in markdown


def test_response_can_be_rescored_offline_with_equivalent_terms() -> None:
    suite, observations = _loaded()
    original_case = next(
        case for case in suite.cases if case.id == "dev-chat-pessoas"
    )
    controlled_case = replace(
        original_case,
        expected=replace(
            original_case.expected,
            required_items=("200m || 200 metros || duzentos metros",),
        ),
    )
    original_observation = next(
        item
        for item in observations.observations
        if item.case_id == original_case.id
    )
    controlled_observation = replace(
        original_observation,
        items=(),
        response="A distancia minima determinada foi de 200 metros.",
    )

    report = run_integrated_benchmark(
        replace(suite, cases=(controlled_case,)),
        replace(observations, observations=(controlled_observation,)),
        split="development",
    )

    assert report.engines[0].metrics.item_recall == 1.0


def test_forbidden_item_is_detected_directly_in_saved_response() -> None:
    suite, observations = _loaded()
    original_case = next(
        case for case in suite.cases if case.id == "test-tese-autoria"
    )
    controlled_case = replace(
        original_case,
        expected=replace(
            original_case.expected,
            forbidden_items=(
                "nulidade definitiva || nulidade confirmada || nulidade foi confirmada",
            ),
        ),
        review_status="legal_approved",
    )
    original_observation = next(
        item
        for item in observations.observations
        if item.case_id == original_case.id
    )
    controlled_observation = replace(
        original_observation,
        items=(),
        response="A nulidade foi confirmada sem necessidade de revisao.",
    )

    report = run_integrated_benchmark(
        replace(suite, cases=(controlled_case,)),
        replace(observations, observations=(controlled_observation,)),
        split="test",
    )

    assert report.engines[0].metrics.false_positive_case_rate == 1.0
    assert report.engines[0].gate_status == "failed"
