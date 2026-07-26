from preparador_audiencia.evaluation import (
    EvaluationCase,
    evaluate_llm_models,
    evaluate_retrieval_case,
    score_llm_answer,
)
from preparador_audiencia.llm import LLMAnswer
from preparador_audiencia.search import SearchResult


class FakeLLMClient:
    model = "fake:fake-model"

    def answer(self, pergunta: str, sources: list[SearchResult]) -> LLMAnswer:
        return LLMAnswer(
            model=self.model,
            answer="A audiencia aparece nas fontes e deve ser conferida [p. 2].",
            latency_ms=10,
        )


def test_evaluate_retrieval_case_scores_expected_page_and_terms() -> None:
    case = EvaluationCase(
        id="audiencia",
        pergunta="Quando sera a audiencia?",
        expected_pages=[2],
        expected_terms=["audiencia"],
    )
    sources = [
        SearchResult(
            text="Designada audiencia de instrucao.",
            page_number=2,
            chunk_index=0,
            document_type="audiencia",
            score=0.9,
        )
    ]

    result = evaluate_retrieval_case(case, sources)

    assert result.hit is True
    assert result.reciprocal_rank == 1.0
    assert result.score == 1.0


def test_score_llm_answer_rewards_citation_and_expected_terms() -> None:
    case = evaluate_retrieval_case(
        EvaluationCase(
            id="audiencia",
            pergunta="Quando sera a audiencia?",
            expected_pages=[2],
            expected_terms=["audiencia"],
        ),
        [
            SearchResult(
                text="Designada audiencia.",
                page_number=2,
                chunk_index=0,
                document_type="audiencia",
                score=0.9,
            )
        ],
    )
    answer = LLMAnswer(
        model="fake",
        answer="A audiencia foi mencionada no processo [p. 2].",
        latency_ms=10,
    )

    assert score_llm_answer(answer, case) == 1.0


def test_score_llm_answer_reads_expected_page_in_grouped_citation() -> None:
    case = evaluate_retrieval_case(
        EvaluationCase(
            id="datas",
            pergunta="Quais datas aparecem?",
            expected_pages=[7],
            expected_terms=["denuncia"],
        ),
        [SearchResult("Denuncia recebida.", 7, 0, None, 0.9)],
    )
    answer = LLMAnswer(
        model="fake",
        answer="A denuncia foi recebida na data informada [p. 1, 7].",
        latency_ms=10,
    )

    assert score_llm_answer(answer, case) == 1.0


def test_score_llm_answer_matches_term_split_by_line_break() -> None:
    case = evaluate_retrieval_case(
        EvaluationCase(
            id="saude",
            pergunta="Qual era a condicao de saude?",
            expected_pages=[13],
            expected_terms=["esquisenfalia cerebral bilateral"],
        ),
        [SearchResult("esquisenfalia\ncerebral bilateral", 13, 0, None, 0.9)],
    )
    answer = LLMAnswer(
        model="fake",
        answer="Consta esquisenfalia\ncerebral bilateral [p. 13].",
        latency_ms=10,
    )

    assert score_llm_answer(answer, case) == 1.0


def test_evaluate_llm_models_uses_injected_clients() -> None:
    case = evaluate_retrieval_case(
        EvaluationCase(
            id="audiencia",
            pergunta="Quando sera a audiencia?",
            expected_pages=[2],
            expected_terms=["audiencia"],
        ),
        [
            SearchResult(
                text="Designada audiencia.",
                page_number=2,
                chunk_index=0,
                document_type="audiencia",
                score=0.9,
            )
        ],
    )

    results = evaluate_llm_models(
        models=["fake:fake-model"],
        retrieval_cases=[case],
        clients={"fake:fake-model": FakeLLMClient()},
    )

    assert results[0].model == "fake:fake-model"
    assert results[0].score == 1.0
