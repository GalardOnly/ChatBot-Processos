import pytest

from preparador_audiencia.llm import (
    GeminiChatClient,
    OllamaChatClient,
    OpenAICompatibleChatClient,
    _safe_error,
    _strip_thinking,
    llm_client_from_spec,
)


def test_llm_client_from_spec_builds_openai_compatible_client(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-key")

    client = llm_client_from_spec("deepseek:deepseek-chat")

    assert isinstance(client, OpenAICompatibleChatClient)
    assert client.model == "deepseek:deepseek-chat"


def test_llm_client_from_spec_builds_gemini_client(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    client = llm_client_from_spec("gemini:gemini-1.5-flash")

    assert isinstance(client, GeminiChatClient)
    assert client.model == "gemini:gemini-1.5-flash"


def test_llm_client_from_spec_builds_ollama_client() -> None:
    client = llm_client_from_spec("ollama:deepseek-r1:latest")

    assert isinstance(client, OllamaChatClient)
    assert client.model == "ollama:deepseek-r1:latest"


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


def test_strip_thinking_removes_deepseek_reasoning() -> None:
    answer = _strip_thinking("<think>raciocinio interno</think>\nResposta final [p. 1].")

    assert answer == "Resposta final [p. 1]."
