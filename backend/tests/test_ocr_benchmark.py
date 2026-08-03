import json

import fitz

from preparador_audiencia.ocr_benchmark import (
    OcrBenchmarkEngineSpec,
    OcrBenchmarkSuite,
    OcrGoldCase,
    load_ocr_benchmark_suite,
    normalized_phrase_recall,
    render_ocr_benchmark_markdown,
    run_ocr_benchmark,
    write_ocr_benchmark_report,
)


class FakeOcrEngine:
    def __init__(self, texts: dict[int, str]) -> None:
        self.texts = texts

    def extract_page_text(self, page: fitz.Page) -> str:
        return self.texts[page.number + 1]


def test_phrase_recall_ignores_case_accents_and_punctuation() -> None:
    matched, missing, recall = normalized_phrase_recall(
        "A VITIMA declarou: voce vai morrer!",
        ["a v\u00edtima declarou", "voc\u00ea vai morrer"],
    )

    assert matched == ("a v\u00edtima declarou", "voc\u00ea vai morrer")
    assert missing == ()
    assert recall == 1.0


def test_phrase_recall_penalizes_glued_words() -> None:
    matched, missing, recall = normalized_phrase_recall(
        "avitimadeclarouvocevaimorrer",
        ["a vitima declarou", "voce vai morrer"],
    )

    assert matched == ()
    assert missing == ("a vitima declarou", "voce vai morrer")
    assert recall == 0.0


def test_run_records_completed_and_unavailable_engines(tmp_path) -> None:
    pdf_path = tmp_path / "processo.pdf"
    document = fitz.open()
    document.new_page()
    document.new_page()
    document.save(pdf_path)
    document.close()
    suite = OcrBenchmarkSuite(
        id="fixture",
        description="Teste",
        human_review_status="approved",
        cases=(
            OcrGoldCase(1, "declaracao", ("termo de declaracao",)),
            OcrGoldCase(2, "interrogatorio", ("termo de interrogatorio",)),
        ),
    )
    specs = [
        OcrBenchmarkEngineSpec(
            name="motor-a",
            family="familia-a",
            factory=lambda: FakeOcrEngine(
                {
                    1: "Termo de declaracao",
                    2: "Termo de interrogatorio",
                }
            ),
        ),
        OcrBenchmarkEngineSpec(
            name="motor-b",
            family="familia-b",
            factory=lambda: _raise(RuntimeError("modelo ausente")),
        ),
    ]

    report = run_ocr_benchmark(pdf_path, suite, specs)

    assert report.engines[0].status == "concluido"
    assert report.engines[0].phrase_recall == 1.0
    assert report.engines[1].status == "indisponivel"
    assert "modelo ausente" in (report.engines[1].error or "")
    assert report.comparison_ready is False
    assert report.gate_passed is False


def test_gate_requires_two_engine_families_and_quality(tmp_path) -> None:
    pdf_path = tmp_path / "processo.pdf"
    document = fitz.open()
    document.new_page()
    document.save(pdf_path)
    document.close()
    suite = OcrBenchmarkSuite(
        id="fixture",
        description="Teste",
        human_review_status="approved",
        cases=(OcrGoldCase(1, "declaracao", ("termo de declaracao",)),),
    )
    specs = [
        OcrBenchmarkEngineSpec(
            name="motor-a",
            family="familia-a",
            factory=lambda: FakeOcrEngine({1: "Termo de declaracao"}),
        ),
        OcrBenchmarkEngineSpec(
            name="motor-b",
            family="familia-b",
            factory=lambda: FakeOcrEngine({1: "Termo de declaracao"}),
        ),
    ]

    report = run_ocr_benchmark(pdf_path, suite, specs)

    assert report.comparison_ready is True
    assert report.gate_passed is True
    assert report.best_engine in {"motor-a", "motor-b"}


def test_gate_requires_human_approved_gold(tmp_path) -> None:
    pdf_path = tmp_path / "processo.pdf"
    document = fitz.open()
    document.new_page()
    document.save(pdf_path)
    document.close()
    suite = OcrBenchmarkSuite(
        id="fixture",
        description="Teste",
        human_review_status="pending",
        cases=(OcrGoldCase(1, "declaracao", ("termo de declaracao",)),),
    )
    specs = [
        OcrBenchmarkEngineSpec(
            name="motor-a",
            family="familia-a",
            factory=lambda: FakeOcrEngine({1: "Termo de declaracao"}),
        ),
        OcrBenchmarkEngineSpec(
            name="motor-b",
            family="familia-b",
            factory=lambda: FakeOcrEngine({1: "Termo de declaracao"}),
        ),
    ]

    report = run_ocr_benchmark(pdf_path, suite, specs)

    assert report.comparison_ready is True
    assert report.gate_passed is False

def test_load_and_write_report(tmp_path) -> None:
    gold_path = tmp_path / "gold.json"
    gold_path.write_text(
        json.dumps(
            {
                "id": "fixture",
                "description": "Teste",
                "human_review_status": "pending",
                "cases": [
                    {
                        "page_number": 1,
                        "label": "declaracao",
                        "expected_phrases": ["termo de declaracao"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    pdf_path = tmp_path / "processo.pdf"
    document = fitz.open()
    document.new_page()
    document.save(pdf_path)
    document.close()
    suite = load_ocr_benchmark_suite(gold_path)
    report = run_ocr_benchmark(
        pdf_path,
        suite,
        [
            OcrBenchmarkEngineSpec(
                name="motor-a",
                family="familia-a",
                factory=lambda: FakeOcrEngine({1: "Termo de declaracao"}),
            )
        ],
    )
    output = tmp_path / "report.json"

    write_ocr_benchmark_report(report, output)

    assert json.loads(output.read_text(encoding="utf-8"))["suite_id"] == "fixture"
    assert "Benchmark de OCR" in render_ocr_benchmark_markdown(report)
    assert output.with_suffix(".md").exists()


def _raise(error: Exception):
    raise error
