import sys
from pathlib import Path

import pytest

from preparador_audiencia.integrated_chat_cli import main

DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
REFERENCE_SUITE_PATH = DATA_ROOT / "reference_suite_multidomain.json"
PROCESS_MAP = [
    "stj-resp-1481531-familia=proc-1",
    "stj-hc-477723-violencia-domestica=proc-2",
    "stj-resp-1876047-saude=proc-3",
]


def test_dry_run_respects_budget_without_copying_database(
    tmp_path, monkeypatch, capsys
) -> None:
    snapshot = tmp_path / "should-not-exist.sqlite3"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "benchmark-chat-publico",
            "--reference-suite",
            str(REFERENCE_SUITE_PATH),
            "--test-process",
            "stj-resp-1876047-saude",
            "--process-map",
            *PROCESS_MAP,
            "--limit-cases",
            "3",
            "--max-llm-calls",
            "6",
            "--database-snapshot",
            str(snapshot),
            "--dry-run",
        ],
    )

    main()

    assert not snapshot.exists()
    output = capsys.readouterr().out
    assert "Casos: 3" in output
    assert "Chamadas planejadas no pior caso: 6" in output
    assert "nenhuma chamada externa" in output.lower()


def test_test_split_requires_explicit_release(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "benchmark-chat-publico",
            "--reference-suite",
            str(REFERENCE_SUITE_PATH),
            "--test-process",
            "stj-resp-1876047-saude",
            "--process-map",
            *PROCESS_MAP,
            "--split",
            "test",
            "--dry-run",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 2
