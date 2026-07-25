from preparador_audiencia.llm import LLMAnswer
from preparador_audiencia.quality import evaluate_legal_quality, parse_quality_evaluation
from preparador_audiencia.search import SearchResult


class FakeJudgeClient:
    model = "groq:fake-judge"

    def complete(self, system_prompt: str, user_prompt: str) -> LLMAnswer:
        return LLMAnswer(
            model=self.model,
            answer=(
                '{"fidelidade_fontes": 5, "completude_juridica": 4, '
                '"utilidade_audiencia": 4, "risco_alucinacao": "baixo", '
                '"pontos_fortes": ["cita pagina"], "problemas": [], '
                '"faltou": ["perguntas para testemunha"], '
                '"veredito": "Boa resposta para triagem inicial."}'
            ),
            latency_ms=10,
        )


def test_parse_quality_evaluation_reads_json_from_markdown_fence() -> None:
    raw = """
```json
{
  "fidelidade_fontes": 5,
  "completude_juridica": 3,
  "utilidade_audiencia": 4,
  "risco_alucinacao": "baixo",
  "pontos_fortes": ["ancorada nas fontes"],
  "problemas": ["faltou separar fato de inferencia"],
  "faltou": ["checklist final"],
  "veredito": "Util, mas incompleta."
}
```
"""

    evaluation = parse_quality_evaluation("groq:judge", raw)

    assert evaluation.fidelidade_fontes == 5
    assert evaluation.completude_juridica == 3
    assert evaluation.risco_alucinacao == "baixo"
    assert evaluation.problemas == ["faltou separar fato de inferencia"]


def test_parse_quality_evaluation_returns_failed_result_for_invalid_json() -> None:
    evaluation = parse_quality_evaluation("groq:judge", "resposta sem json")

    assert evaluation.error is not None
    assert evaluation.fidelidade_fontes == 1


def test_evaluate_legal_quality_uses_injected_llm_client(monkeypatch) -> None:
    monkeypatch.setattr(
        "preparador_audiencia.quality.llm_client_from_spec",
        lambda spec: FakeJudgeClient(),
    )
    sources = [
        SearchResult(
            text="Audiencia designada.",
            page_number=1,
            chunk_index=0,
            document_type=None,
            score=0.9,
        )
    ]

    evaluation = evaluate_legal_quality(
        pergunta="Existe audiencia?",
        resposta="Sim, ha audiencia designada [p. 1].",
        sources=sources,
        evaluator_model="groq:fake-judge",
    )

    assert evaluation.evaluator_model == "groq:fake-judge"
    assert evaluation.fidelidade_fontes == 5
    assert evaluation.faltou == ["perguntas para testemunha"]
