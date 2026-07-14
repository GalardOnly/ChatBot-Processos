import argparse

import pytest

from preparador_audiencia.eval_cli import estimate_llm_calls, validate_llm_budget


def test_estimate_llm_calls_multiplies_cases_by_models() -> None:
    assert estimate_llm_calls(cases_count=3, llm_models=["groq:a", "openai:b"]) == 6


def test_validate_llm_budget_blocks_over_limit() -> None:
    parser = argparse.ArgumentParser()

    with pytest.raises(SystemExit):
        validate_llm_budget(
            planned_calls=5,
            max_calls=4,
            allow_over_limit=False,
            parser=parser,
        )


def test_validate_llm_budget_allows_explicit_override() -> None:
    parser = argparse.ArgumentParser()

    validate_llm_budget(
        planned_calls=5,
        max_calls=4,
        allow_over_limit=True,
        parser=parser,
    )
