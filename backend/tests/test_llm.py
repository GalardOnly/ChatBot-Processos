import pytest

from preparador_audiencia.llm import (
    GeminiChatClient,
    OpenAICompatibleChatClient,
    _safe_error,
    llm_client_from_spec,
)


def test_llm_client_from_spec_builds_groq_client(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "fake-key")

    client = llm_client_from_spec("groq:llama-3.1-8b-instant")

    assert isinstance(client, OpenAICompatibleChatClient)
    assert client.model == "groq:llama-3.1-8b-instant"


def test_llm_client_from_spec_builds_gemini_client(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    client = llm_client_from_spec("gemini:gemini-1.5-flash")

    assert isinstance(client, GeminiChatClient)
    assert client.model == "gemini:gemini-1.5-flash"


def test_llm_client_from_spec_requires_provider_prefix() -> None:
    with pytest.raises(ValueError):
        llm_client_from_spec("modelo-sem-provedor")


def test_safe_error_redacts_query_key_and_env_secret(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "secret-value")

    message = _safe_error(
        RuntimeError(
            "erro em https://example.test/generate?key=secret-value com token secret-value"
        )
    )

    assert "secret-value" not in message
    assert "key=[REDACTED]" in message
