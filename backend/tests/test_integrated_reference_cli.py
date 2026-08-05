import json
import sys
from pathlib import Path

from preparador_audiencia.integrated_reference_cli import main
from preparador_audiencia.reference_suite import load_reference_suite

DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
REFERENCE_SUITE_PATH = DATA_ROOT / "reference_suite_multidomain.json"
TEST_PROCESS_ID = "stj-resp-1876047-saude"


def test_cli_dry_run_does_not_write_files(tmp_path, monkeypatch, capsys) -> None:
    suite = load_reference_suite(REFERENCE_SUITE_PATH)
    payload = {
        "suite_id": suite.id,
        "embedding_model": "hash",
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
                                "pages": [case.expected_pages[0]],
                                "hit": True,
                                "latency_ms": 10,
                            },
                        }
                        for case in process.cases
                    ]
                },
            }
            for process in suite.processes
        ],
    }
    reference_report = tmp_path / "reference.json"
    reference_report.write_text(json.dumps(payload), encoding="utf-8")
    suite_output = tmp_path / "suite-output.json"
    observations_output = tmp_path / "observations-output.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "adaptar-benchmark-publico",
            "--reference-suite",
            str(REFERENCE_SUITE_PATH),
            "--reference-report",
            str(reference_report),
            "--test-process",
            TEST_PROCESS_ID,
            "--suite-output",
            str(suite_output),
            "--observations-output",
            str(observations_output),
            "--dry-run",
        ],
    )

    main()

    assert not suite_output.exists()
    assert not observations_output.exists()
    output = capsys.readouterr().out
    assert "development: 6 casos" in output
    assert "test: 4 casos" in output
    assert "Nenhum arquivo foi gravado" in output
