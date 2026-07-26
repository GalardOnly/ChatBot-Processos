from preparador_audiencia.response_benchmark_cli import estimate_response_llm_calls


def test_estimate_response_llm_calls_uses_worst_case_budget() -> None:
    assert estimate_response_llm_calls(cases_count=3) == 9
