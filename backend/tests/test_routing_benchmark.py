from dataclasses import dataclass

import pytest

from preparador_audiencia.evaluation import EvaluationCase
from preparador_audiencia.repositories import ChunkRecord
from preparador_audiencia.routing_benchmark import (
    generate_cases_from_chunks,
    render_routing_benchmark_markdown,
    run_routing_benchmark,
)
from preparador_audiencia.search import SearchResult


@dataclass(frozen=True)
class FakeRoute:
    query: str
    area: str | None = None
    audiencia: str | None = None
    guides: tuple[object, ...] = ()

    def search_query(self) -> str:
        return self.query


def _chunk(
    *,
    chunk_id: int,
    page: int,
    text: str,
    document_type: str | None = None,
) -> ChunkRecord:
    return ChunkRecord(
        id=chunk_id,
        processo_id="proc_benchmark",
        page_number=page,
        chunk_index=0,
        text=text,
        document_type=document_type,
        source_confidence="alta",
        vector_id=f"vector-{chunk_id}",
        created_at="2026-07-26T12:00:00+00:00",
    )


def _result(page: int, text: str, score: float = 0.9) -> SearchResult:
    return SearchResult(
        text=text,
        page_number=page,
        chunk_index=0,
        document_type=None,
        score=score,
    )


def test_generate_cases_from_chunks_respects_limit_and_builds_expectations() -> None:
    chunks = [
        _chunk(
            chunk_id=1,
            page=3,
            text=(
                "A audiencia de instrucao foi designada para 20 de agosto de 2026, "
                "com intimacao das partes e testemunhas. A decisao determinou que a defesa "
                "apresente previamente o rol de testemunhas e informou que os depoimentos "
                "serao colhidos presencialmente, respeitada a ordem prevista na legislacao."
            ),
            document_type="decisao",
        ),
        _chunk(
            chunk_id=2,
            page=8,
            text=(
                "O acusado declarou que estava trabalhando no horario dos fatos "
                "e indicou duas testemunhas de defesa. Segundo o interrogatorio, documentos "
                "do empregador poderiam confirmar a jornada narrada. A defesa requereu a "
                "juntada desses registros e a oitiva das pessoas indicadas pelo acusado."
            ),
            document_type="depoimento",
        ),
        _chunk(
            chunk_id=3,
            page=12,
            text=(
                "O laudo pericial registrou ausencia de lesoes e foi juntado aos autos "
                "antes da apresentacao das alegacoes finais. O documento descreveu o metodo "
                "empregado no exame, os vestigios analisados e as conclusoes do perito. "
                "As partes foram intimadas para apresentar quesitos complementares."
            ),
            document_type="laudo",
        ),
    ]

    cases = generate_cases_from_chunks(chunks, limit=2)

    assert 0 < len(cases) <= 2
    assert all(isinstance(case, EvaluationCase) for case in cases)
    assert all(case.expected_pages for case in cases)
    assert all(case.expected_terms for case in cases)
    assert all(set(case.expected_pages) <= {3, 8, 12} for case in cases)
    assert all(all(term.strip() for term in case.expected_terms) for case in cases)


def test_run_routing_benchmark_compares_raw_and_routed_search(monkeypatch) -> None:
    cases = [
        EvaluationCase(
            id="melhora",
            pergunta="Quando sera a audiencia?",
            expected_pages=[1],
            expected_terms=["audiencia"],
        ),
        EvaluationCase(
            id="piora",
            pergunta="Onde esta o depoimento?",
            expected_pages=[2],
            expected_terms=["depoimento"],
        ),
        EvaluationCase(
            id="empate",
            pergunta="O que diz o laudo?",
            expected_pages=[3],
            expected_terms=["laudo"],
        ),
    ]
    routed_queries = {
        "Quando sera a audiencia?": "Quando sera a audiencia? designacao intimacao",
        "Onde esta o depoimento?": "Onde esta o depoimento? prova oral testemunhas",
        "O que diz o laudo?": "O que diz o laudo? pericia documento tecnico",
    }
    results_by_query = {
        "Quando sera a audiencia?": [_result(9, "Trecho sem a informacao esperada.")],
        routed_queries["Quando sera a audiencia?"]: [
            _result(1, "A audiencia foi designada para agosto.")
        ],
        "Onde esta o depoimento?": [_result(2, "O depoimento consta nesta pagina.")],
        routed_queries["Onde esta o depoimento?"]: [
            _result(7, "Relato de uma testemunha."),
            _result(2, "Trecho sem o termo esperado."),
        ],
        "O que diz o laudo?": [_result(3, "O laudo afastou a existencia de lesoes.")],
        routed_queries["O que diz o laudo?"]: [
            _result(3, "O laudo afastou a existencia de lesoes.")
        ],
    }
    multi_query_calls: list[dict[str, object]] = []
    route_calls: list[str] = []

    def fake_search_process_queries_configured(**kwargs) -> list[SearchResult]:
        multi_query_calls.append(kwargs)
        queries = kwargs["queries"]
        selected_query = str(queries[-1][0])
        return results_by_query[selected_query]

    def fake_route_question(pergunta: str) -> FakeRoute:
        route_calls.append(pergunta)
        return FakeRoute(routed_queries[pergunta])

    monkeypatch.setattr(
        "preparador_audiencia.routing_benchmark.search_process_queries_configured",
        fake_search_process_queries_configured,
    )
    monkeypatch.setattr(
        "preparador_audiencia.routing_benchmark.route_question",
        fake_route_question,
    )

    report = run_routing_benchmark(
        processo_id="proc_benchmark",
        cases=cases,
        top_k=5,
        embedding_model="legal-ensemble",
        llm_cases=0,
        generator_model="gemini:modelo-nao-deve-ser-usado",
        fallback_model="groq:modelo-nao-deve-ser-usado",
    )

    assert route_calls == [case.pergunta for case in cases]
    assert len(multi_query_calls) == len(cases) * 2
    assert all(call["processo_id"] == "proc_benchmark" for call in multi_query_calls)
    assert all(call["top_k"] == 5 for call in multi_query_calls)
    assert all(
        call["embedding_spec"] == "legal-ensemble"
        for call in multi_query_calls
    )

    assert report.processo_id == "proc_benchmark"
    assert report.total_cases == 3
    assert report.top_k == 5
    assert report.raw_hit_rate == pytest.approx(2 / 3, abs=0.0001)
    assert report.raw_mrr == pytest.approx(2 / 3, abs=0.0001)
    assert report.raw_average_score == pytest.approx(2 / 3, abs=0.0001)
    assert report.routed_hit_rate == 1.0
    assert report.routed_mrr == pytest.approx(5 / 6, abs=0.0001)
    assert report.routed_average_score == pytest.approx(0.9083, abs=0.0001)
    assert report.raw_average_latency_ms >= 0
    assert report.routed_average_latency_ms >= 0
    assert report.improved_cases == 1
    assert report.degraded_cases == 1
    assert report.tied_cases == 1


def test_run_routing_benchmark_uses_original_and_enriched_queries(monkeypatch) -> None:
    seen_queries: list[str] = []
    case = EvaluationCase(
        id="custodia",
        pergunta="A prisao foi legal?",
        expected_pages=[4],
        expected_terms=["prisao"],
    )

    def fake_search_process_queries_configured(**kwargs) -> list[SearchResult]:
        seen_queries.extend(str(query) for query, _weight in kwargs["queries"])
        return [_result(4, "A prisao em flagrante foi homologada.")]

    monkeypatch.setattr(
        "preparador_audiencia.routing_benchmark.search_process_queries_configured",
        fake_search_process_queries_configured,
    )
    monkeypatch.setattr(
        "preparador_audiencia.routing_benchmark.route_question",
        lambda pergunta: FakeRoute(f"{pergunta} audiencia de custodia flagrante"),
    )

    run_routing_benchmark(
        processo_id="proc_benchmark",
        cases=[case],
        embedding_model=None,
        llm_cases=0,
    )

    assert seen_queries == [
        "A prisao foi legal?",
        "A prisao foi legal?",
        "A prisao foi legal? audiencia de custodia flagrante",
    ]


def test_render_routing_benchmark_markdown_reports_comparison(monkeypatch) -> None:
    case = EvaluationCase(
        id="audiencia",
        pergunta="Quando sera a audiencia?",
        expected_pages=[6],
        expected_terms=["audiencia"],
    )

    monkeypatch.setattr(
        "preparador_audiencia.routing_benchmark.search_process_queries_configured",
        lambda **kwargs: [_result(6, "A audiencia foi marcada.")],
    )
    monkeypatch.setattr(
        "preparador_audiencia.routing_benchmark.route_question",
        lambda pergunta: FakeRoute(f"{pergunta} designacao"),
    )

    report = run_routing_benchmark(
        processo_id="proc_benchmark",
        cases=[case],
        llm_cases=0,
    )
    markdown = render_routing_benchmark_markdown(report)

    assert "Benchmark A/B da triagem interna" in markdown
    assert "Pergunta bruta" in markdown
    assert "Com triagem" in markdown
    assert "Hit rate" in markdown
    assert "MRR" in markdown
    assert "Score medio" in markdown
    assert "Latencia media" in markdown
    assert "Casos que melhoraram" in markdown
    assert "Casos que pioraram" in markdown
    assert "Empates" in markdown
