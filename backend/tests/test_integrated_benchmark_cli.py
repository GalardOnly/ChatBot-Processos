import sys
from pathlib import Path

from preparador_audiencia.integrated_benchmark_cli import main

DATA_ROOT = Path(__file__).resolve().parents[1] / "data"


def test_dry_run_does_not_write_report(tmp_path, monkeypatch, capsys) -> None:
    output = tmp_path / "benchmark.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "benchmark-integrado",
            "--suite",
            str(DATA_ROOT / "integrated_benchmark_v01.json"),
            "--observations",
            str(DATA_ROOT / "integrated_benchmark_observations_calibration.json"),
            "--split",
            "test",
            "--output",
            str(output),
            "--dry-run",
        ],
    )

    main()

    assert not output.exists()
    captured = capsys.readouterr().out
    assert "Split: test" in captured
    assert "Nenhuma chamada externa" in captured
