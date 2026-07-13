import pytest

from preparador_audiencia.llm import (
    GeminiChatClient,
    OpenAICompatibleChatClient,
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


def test_llm_client_from_spec_requires_provider_prefix() -> None:
    with pytest.raises(ValueError):
        llm_client_from_spec("modelo-sem-provedor")
