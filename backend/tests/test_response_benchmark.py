from preparador_audiencia.chat import ChatResult
from preparador_audiencia.evaluation import EvaluationCase
from preparador_audiencia.quality import LegalQualityEvaluation
from preparador_audiencia.response_benchmark import (
    render_response_benchmark_markdown,
    run_response_quality_benchmark,
)
from preparador_audiencia.search import SearchResult


def test_run_response_quality_benchmark_scores_complete_chat_flow(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(tmp_path / "test.sqlite3"))

    def fake_answer_process_question(**kwargs) -> ChatResult:
        source = SearchResult(
            text="A audiencia foi designada para a pagina indicada.",
            page_number=2,
            chunk_index=0,
            document_type="decisao",
            score=0.91,
        )
        quality = LegalQualityEvaluation(
            evaluator_model=kwargs["evaluator_model"],
            fidelidade_fontes=5,
            completude_juridica=4,
            utilidade_audiencia=5,
            risco_alucinacao="baixo",
            pontos_fortes=["resposta citou a fonte"],
            problemas=[],
            faltou=[],
            veredito="Resposta adequada para a PoC.",
            raw_response="{}",
        )
        return ChatResult(
            pergunta=kwargs["pergunta"],
            resposta="A audiencia aparece na pagina 2 [p. 2].",
            modelo=kwargs["primary_model"],
            fallback_usado=False,
            fontes=[source],
            avaliacao=quality,
        )

    monkeypatch.setattr(
        "preparador_audiencia.response_benchmark.answer_process_question",
        fake_answer_process_question,
    )

    report = run_response_quality_benchmark(
        processo_id="proc_teste",
        cases=[
            EvaluationCase(
                id="audiencia",
                pergunta="Quando sera a audiencia?",
                expected_pages=[2],
                expected_terms=["audiencia"],
            )
        ],
        generator_model="gemini:teste",
        fallback_model="groq:teste",
        evaluator_model="groq:avaliador",
        embedding_model="legal-ensemble",
        index_before_search=False,
    )

    assert report.average_fidelidade_fontes == 5
    assert report.average_completude_juridica == 4
    assert report.average_utilidade_audiencia == 5
    assert report.high_risk_count == 0
    assert report.cases[0].source_pages == [2]
    assert report.cases[0].generator_model == "gemini:teste"


def test_render_response_benchmark_markdown_includes_scores(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(tmp_path / "test.sqlite3"))

    def fake_answer_process_question(**kwargs) -> ChatResult:
        quality = LegalQualityEvaluation(
            evaluator_model=kwargs["evaluator_model"],
            fidelidade_fontes=2,
            completude_juridica=3,
            utilidade_audiencia=2,
            risco_alucinacao="alto",
            pontos_fortes=[],
            problemas=["afirmacao sem fonte"],
            faltou=["citar pagina"],
            veredito="Resposta arriscada.",
            raw_response="{}",
        )
        return ChatResult(
            pergunta=kwargs["pergunta"],
            resposta="Resposta incompleta.",
            modelo=kwargs["primary_model"],
            fallback_usado=False,
            fontes=[],
            avaliacao=quality,
        )

    monkeypatch.setattr(
        "preparador_audiencia.response_benchmark.answer_process_question",
        fake_answer_process_question,
    )
    report = run_response_quality_benchmark(
        processo_id="proc_teste",
        cases=[
            EvaluationCase(
                id="risco",
                pergunta="Qual foi o resultado?",
                expected_pages=[],
                expected_terms=[],
            )
        ],
        index_before_search=False,
    )

    markdown = render_response_benchmark_markdown(report)

    assert "Benchmark de Respostas da PoC" in markdown
    assert "2.00/5" in markdown
    assert "Casos com risco alto de alucinacao: `1`" in markdown
