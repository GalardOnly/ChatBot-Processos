from copy import deepcopy
from pathlib import Path

import pytest

from preparador_audiencia.integrated_benchmark import (
    load_integrated_benchmark_suite,
    load_observation_run,
    run_integrated_benchmark,
    write_integrated_benchmark_suite,
    write_observation_run,
)
from preparador_audiencia.integrated_reference_adapter import (
    adapt_reference_benchmark,
)
from preparador_audiencia.reference_suite import load_reference_suite

DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
REFERENCE_SUITE_PATH = DATA_ROOT / "reference_suite_multidomain.json"
TEST_PROCESS_ID = "stj-resp-1876047-saude"


def _reference_suite():
    return load_reference_suite(REFERENCE_SUITE_PATH)


def _report_payload():
    suite = _reference_suite()
    return {
        "suite_id": suite.id,
        "embedding_model": "legal-ensemble",
        "top_k": 5,
        "processes": [
            {
                "reference_id": process.id,
                "routing": {
                    "cases": [
                        {
                            "case_id": case.id,
                            "pergunta": case.pergunta,
                            "expected_pages": case.expected_pages,
                            "routed": {
                                "pages": [case.expected_pages[0], 99],
                                "hit": True,
                                "latency_ms": 25,
                            },
                        }
                        for case in process.cases
                    ]
                },
            }
            for process in suite.processes
        ],
    }


def _adapt():
    return adapt_reference_benchmark(
        _reference_suite(),
        _report_payload(),
        test_process_ids={TEST_PROCESS_ID},
        run_id="test-run",
    )


def test_converts_public_cases_and_keeps_processes_in_single_split() -> None:
    suite, observations = _adapt()

    assert len(suite.cases) == 10
    assert len(observations.observations) == 10
    development_sources = {
        case.source.reference_id
        for case in suite.cases
        if case.split == "development"
    }
    test_sources = {
        case.source.reference_id for case in suite.cases if case.split == "test"
    }
    assert development_sources.isdisjoint(test_sources)
    assert test_sources == {TEST_PROCESS_ID}
    assert all(case.provenance == "public_real" for case in suite.cases)
    assert all(case.review_status == "pending" for case in suite.cases)


def test_round_trip_preserves_sources_and_observations(tmp_path) -> None:
    suite, observations = _adapt()
    suite_path = tmp_path / "suite.json"
    observations_path = tmp_path / "observations.json"

    write_integrated_benchmark_suite(suite, suite_path)
    write_observation_run(observations, observations_path)
    loaded_suite = load_integrated_benchmark_suite(suite_path)
    loaded_observations = load_observation_run(observations_path)

    assert loaded_suite == suite
    assert loaded_observations == observations
    report = run_integrated_benchmark(
        loaded_suite,
        loaded_observations,
        split="test",
    )
    assert report.cases_count == 4
    assert report.gate_status == "not_eligible"
    assert report.engines[0].metrics.label_accuracy == 1.0


def test_rejects_case_with_pages_different_from_reference_suite() -> None:
    payload = deepcopy(_report_payload())
    payload["processes"][0]["routing"]["cases"][0]["expected_pages"] = [999]

    with pytest.raises(ValueError, match="Paginas esperadas divergentes"):
        adapt_reference_benchmark(
            _reference_suite(),
            payload,
            test_process_ids={TEST_PROCESS_ID},
            run_id="invalid",
        )


def test_requires_at_least_one_process_in_each_split() -> None:
    suite = _reference_suite()

    with pytest.raises(ValueError, match="ao menos um processo cada"):
        adapt_reference_benchmark(
            suite,
            _report_payload(),
            test_process_ids={process.id for process in suite.processes},
            run_id="invalid",
        )
