from __future__ import annotations

import json
import re
import time
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

import fitz

from preparador_audiencia.pdf_extraction import has_glued_text, normalize_text

OCR_GATE_MIN_PHRASE_RECALL = 0.90


class OcrBenchmarkEngine(Protocol):
    def extract_page_text(self, page: fitz.Page) -> str:
        """Extrai o texto de uma pagina para avaliacao."""


@dataclass(frozen=True)
class OcrGoldCase:
    page_number: int
    label: str
    expected_phrases: tuple[str, ...]


@dataclass(frozen=True)
class OcrBenchmarkSuite:
    id: str
    description: str
    human_review_status: str
    cases: tuple[OcrGoldCase, ...]


@dataclass(frozen=True)
class OcrBenchmarkEngineSpec:
    name: str
    family: str
    factory: Callable[[], OcrBenchmarkEngine]


@dataclass(frozen=True)
class OcrPageBenchmarkResult:
    page_number: int
    label: str
    elapsed_ms: int
    char_count: int
    word_count: int
    space_ratio: float
    long_token_count: int
    max_token_length: int
    glued_text: bool
    expected_phrase_count: int
    matched_phrases: tuple[str, ...]
    missing_phrases: tuple[str, ...]
    phrase_recall: float


@dataclass(frozen=True)
class OcrEngineBenchmarkResult:
    name: str
    family: str
    status: str
    elapsed_ms: int
    page_count: int
    phrase_recall: float
    glued_page_count: int
    pages: tuple[OcrPageBenchmarkResult, ...]
    error: str | None = None


@dataclass(frozen=True)
class OcrBenchmarkReport:
    suite_id: str
    document_name: str
    human_review_status: str
    gate_min_phrase_recall: float
    best_engine: str | None
    comparison_ready: bool
    gate_passed: bool
    engines: tuple[OcrEngineBenchmarkResult, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def load_ocr_benchmark_suite(path: str | Path) -> OcrBenchmarkSuite:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = tuple(
        OcrGoldCase(
            page_number=int(item["page_number"]),
            label=str(item["label"]),
            expected_phrases=tuple(str(phrase) for phrase in item["expected_phrases"]),
        )
        for item in payload["cases"]
    )
    _validate_suite(cases)
    return OcrBenchmarkSuite(
        id=str(payload["id"]),
        description=str(payload["description"]),
        human_review_status=str(payload["human_review_status"]),
        cases=cases,
    )


def run_ocr_benchmark(
    pdf_path: str | Path,
    suite: OcrBenchmarkSuite,
    engine_specs: Sequence[OcrBenchmarkEngineSpec],
) -> OcrBenchmarkReport:
    path = Path(pdf_path)
    if not path.is_file():
        raise FileNotFoundError(f"PDF nao encontrado: {path}")

    engine_results = tuple(
        _run_engine(path, suite, engine_spec) for engine_spec in engine_specs
    )
    completed = [result for result in engine_results if result.status == "concluido"]
    best = min(completed, key=_engine_rank) if completed else None
    comparison_ready = len({result.family for result in completed}) >= 2
    gate_passed = bool(
        comparison_ready
        and best
        and suite.human_review_status == "approved"
        and best.phrase_recall >= OCR_GATE_MIN_PHRASE_RECALL
        and best.glued_page_count == 0
        and best.page_count == len(suite.cases)
    )
    return OcrBenchmarkReport(
        suite_id=suite.id,
        document_name=path.name,
        human_review_status=suite.human_review_status,
        gate_min_phrase_recall=OCR_GATE_MIN_PHRASE_RECALL,
        best_engine=best.name if best else None,
        comparison_ready=comparison_ready,
        gate_passed=gate_passed,
        engines=engine_results,
    )


def write_ocr_benchmark_report(
    report: OcrBenchmarkReport,
    output_path: str | Path,
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    path.with_suffix(".md").write_text(
        render_ocr_benchmark_markdown(report),
        encoding="utf-8",
    )


def render_ocr_benchmark_markdown(report: OcrBenchmarkReport) -> str:
    lines = [
        "# Benchmark de OCR em depoimentos",
        "",
        f"Suite: `{report.suite_id}`",
        f"Documento: `{report.document_name}`",
        f"Revisao humana do gabarito: `{report.human_review_status}`",
        f"Comparacao entre familias pronta: `{report.comparison_ready}`",
        f"Melhor configuracao disponivel: `{report.best_engine or 'nenhuma'}`",
        f"Gate aprovado: `{report.gate_passed}`",
        "",
    ]
    for engine in report.engines:
        lines.extend(
            [
                f"## {engine.name}",
                "",
                f"Familia: `{engine.family}`",
                f"Status: `{engine.status}`",
                f"Recall de frases: `{engine.phrase_recall:.1%}`",
                f"Paginas com palavras coladas: `{engine.glued_page_count}`",
                f"Tempo total: `{engine.elapsed_ms} ms`",
                f"Erro: `{engine.error or ''}`",
                "",
            ]
        )
        for page in engine.pages:
            lines.extend(
                [
                    f"Pagina {page.page_number}: {page.label}",
                    f"Recall: `{page.phrase_recall:.1%}`",
                    f"Palavras coladas: `{page.glued_text}`",
                    f"Frases ausentes: `{', '.join(page.missing_phrases) or 'nenhuma'}`",
                    f"Tempo: `{page.elapsed_ms} ms`",
                    "",
                ]
            )
    return "\n".join(lines)


def normalized_phrase_recall(
    text: str,
    expected_phrases: Sequence[str],
) -> tuple[tuple[str, ...], tuple[str, ...], float]:
    normalized_text = _normalize_for_comparison(text)
    matched = tuple(
        phrase
        for phrase in expected_phrases
        if _normalize_for_comparison(phrase) in normalized_text
    )
    missing = tuple(phrase for phrase in expected_phrases if phrase not in matched)
    recall = len(matched) / len(expected_phrases) if expected_phrases else 1.0
    return matched, missing, recall


def _run_engine(
    pdf_path: Path,
    suite: OcrBenchmarkSuite,
    engine_spec: OcrBenchmarkEngineSpec,
) -> OcrEngineBenchmarkResult:
    started = time.perf_counter()
    try:
        engine = engine_spec.factory()
    except Exception as exc:
        return _failed_engine_result(engine_spec, started, "indisponivel", exc)

    page_results: list[OcrPageBenchmarkResult] = []
    try:
        with fitz.open(pdf_path) as document:
            _validate_document_pages(document.page_count, suite.cases)
            for case in suite.cases:
                page_started = time.perf_counter()
                text = normalize_text(engine.extract_page_text(document[case.page_number - 1]))
                page_results.append(_page_result(case, text, _elapsed_ms(page_started)))
    except Exception as exc:
        return _failed_engine_result(engine_spec, started, "erro", exc)

    expected_count = sum(page.expected_phrase_count for page in page_results)
    matched_count = sum(len(page.matched_phrases) for page in page_results)
    return OcrEngineBenchmarkResult(
        name=engine_spec.name,
        family=engine_spec.family,
        status="concluido",
        elapsed_ms=_elapsed_ms(started),
        page_count=len(page_results),
        phrase_recall=matched_count / expected_count if expected_count else 1.0,
        glued_page_count=sum(page.glued_text for page in page_results),
        pages=tuple(page_results),
    )


def _page_result(
    case: OcrGoldCase,
    text: str,
    elapsed_ms: int,
) -> OcrPageBenchmarkResult:
    tokens = re.findall(r"\S+", text)
    matched, missing, recall = normalized_phrase_recall(text, case.expected_phrases)
    return OcrPageBenchmarkResult(
        page_number=case.page_number,
        label=case.label,
        elapsed_ms=elapsed_ms,
        char_count=len(text),
        word_count=len(tokens),
        space_ratio=text.count(" ") / len(text) if text else 0.0,
        long_token_count=sum(len(token) >= 40 for token in tokens),
        max_token_length=max((len(token) for token in tokens), default=0),
        glued_text=has_glued_text(text),
        expected_phrase_count=len(case.expected_phrases),
        matched_phrases=matched,
        missing_phrases=missing,
        phrase_recall=recall,
    )


def _failed_engine_result(
    engine_spec: OcrBenchmarkEngineSpec,
    started: float,
    status: str,
    error: Exception,
) -> OcrEngineBenchmarkResult:
    return OcrEngineBenchmarkResult(
        name=engine_spec.name,
        family=engine_spec.family,
        status=status,
        elapsed_ms=_elapsed_ms(started),
        page_count=0,
        phrase_recall=0.0,
        glued_page_count=0,
        pages=(),
        error=f"{type(error).__name__}: {error}",
    )


def _engine_rank(result: OcrEngineBenchmarkResult) -> tuple[float, int, int]:
    return (-result.phrase_recall, result.glued_page_count, result.elapsed_ms)


def _normalize_for_comparison(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    only_words = re.sub(r"[^a-z0-9]+", " ", without_accents)
    return " ".join(only_words.split())


def _validate_suite(cases: tuple[OcrGoldCase, ...]) -> None:
    if not cases:
        raise ValueError("A suite de OCR precisa ter pelo menos um caso.")
    page_numbers = [case.page_number for case in cases]
    if any(page_number < 1 for page_number in page_numbers):
        raise ValueError("Os numeros de pagina da suite comecam em 1.")
    if len(page_numbers) != len(set(page_numbers)):
        raise ValueError("A suite de OCR nao pode repetir paginas.")
    if any(not case.expected_phrases for case in cases):
        raise ValueError("Cada pagina precisa ter ao menos uma frase esperada.")


def _validate_document_pages(
    document_page_count: int,
    cases: tuple[OcrGoldCase, ...],
) -> None:
    highest_page = max(case.page_number for case in cases)
    if highest_page > document_page_count:
        raise ValueError(
            f"A suite pede a pagina {highest_page}, mas o PDF tem "
            f"{document_page_count} paginas."
        )


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1_000)
