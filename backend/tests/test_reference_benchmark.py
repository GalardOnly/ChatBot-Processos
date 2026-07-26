from dataclasses import replace

import pytest

from preparador_audiencia.reference_benchmark import (
    PreparedReferenceProcess,
    ensure_reference_document,
    render_reference_benchmark_markdown,
    run_reference_benchmark,
)
from preparador_audiencia.reference_suite import (
    ReferenceCase,
    ReferenceProcess,
    ReferenceSuite,
)
from preparador_audiencia.routing_benchmark import RoutingBenchmarkReport


def _case(case_id: str, status: str = "pending") -> ReferenceCase:
    return ReferenceCase(
        id=case_id,
        pergunta=f"Pergunta {case_id}?",
        expected_pages=[1],
        expected_terms=["termo"],
        review_status=status,
        reviewer=None if status == "pending" else "Revisor",
    )


def _process(process_id: str = "processo-1") -> ReferenceProcess:
    return ReferenceProcess(
        id=process_id,
        domain="penal",
        document=f"{process_id}.pdf",
        source="STJ",
        source_url=f"https://example.test/{process_id}.pdf",
        sha256=None,
        cases=[_case("caso-1"), _case("caso-2", "approved")],
    )


def _routing_report(processo_id: str, total: int = 2) -> RoutingBenchmarkReport:
    return RoutingBenchmarkReport(
        processo_id=processo_id,
        embedding_model="legal-ensemble",
        top_k=5,
        total_cases=total,
        raw_hit_rate=0.5,
        routed_hit_rate=1.0,
        raw_mrr=0.25,
        routed_mrr=0.75,
        raw_average_score=0.5,
        routed_average_score=0.8,
        raw_average_latency_ms=10,
        routed_average_latency_ms=20,
        improved_cases=1,
        degraded_cases=0,
        tied_cases=total - 1,
        routed_cases_with_guides=1,
        llm_fallback_count=0,
        cases=[],
        llm_cases=[],
    )


def test_ensure_reference_document_downloads_and_validates_pdf(tmp_path) -> None:
    process = _process()

    path = ensure_reference_document(
        process,
        tmp_path,
        download_missing=True,
        fetcher=lambda _url: b"%PDF-1.7\nconteudo",
    )

    assert path.name == "processo-1.pdf"
    assert path.read_bytes().startswith(b"%PDF")


def test_ensure_reference_document_rejects_invalid_content(tmp_path) -> None:
    with pytest.raises(ValueError, match="nao retornou um PDF"):
        ensure_reference_document(
            _process(),
            tmp_path,
            download_missing=True,
            fetcher=lambda _url: b"<html>erro</html>",
        )


def test_ensure_reference_document_checks_sha256(tmp_path) -> None:
    process = replace(_process(), sha256="0" * 64)
    (tmp_path / process.document).write_bytes(b"%PDF-1.7\nconteudo")

    with pytest.raises(ValueError, match="SHA-256 divergente"):
        ensure_reference_document(process, tmp_path)


def test_run_reference_benchmark_aggregates_processes(monkeypatch, tmp_path) -> None:
    suite = ReferenceSuite(
        id="suite-1",
        processes=[_process("processo-1"), _process("processo-2")],
    )

    def fake_prepare(process, samples_root, **kwargs) -> PreparedReferenceProcess:
        return PreparedReferenceProcess(
            reference_id=process.id,
            domain=process.domain,
            processo_id=f"db-{process.id}",
            document=process.document,
            page_count=10,
            chunk_count=20,
            reused=True,
        )

    monkeypatch.setattr(
        "preparador_audiencia.reference_benchmark.prepare_reference_process",
        fake_prepare,
    )
    monkeypatch.setattr(
        "preparador_audiencia.reference_benchmark.run_routing_benchmark",
        lambda processo_id, cases, **kwargs: _routing_report(processo_id, len(cases)),
    )

    report = run_reference_benchmark(
        suite,
        tmp_path,
        included_statuses={"approved"},
        embedding_model="legal-ensemble",
    )

    assert report.total_processes == 2
    assert report.total_cases == 2
    assert report.review_status_counts == {"approved": 2}
    assert report.raw_hit_rate == 0.5
    assert report.routed_hit_rate == 1.0
    assert report.improved_cases == 2
    assert report.degraded_cases == 0
    assert "processo-1" in render_reference_benchmark_markdown(report)


def test_run_reference_benchmark_rejects_rejected_status(tmp_path) -> None:
    suite = ReferenceSuite(id="suite-1", processes=[_process()])

    with pytest.raises(ValueError, match="Status nao executaveis"):
        run_reference_benchmark(
            suite,
            tmp_path,
            included_statuses={"rejected"},
        )
