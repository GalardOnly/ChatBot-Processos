from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from preparador_audiencia.search import SearchResult

OPENAI_COMPATIBLE_ENDPOINTS = {
    "groq": ("GROQ_API_KEY", "https://api.groq.com/openai/v1/chat/completions"),
    "openai": ("OPENAI_API_KEY", "https://api.openai.com/v1/chat/completions"),
    "deepseek": ("DEEPSEEK_API_KEY", "https://api.deepseek.com/chat/completions"),
}
GEMINI_ENDPOINT_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


@dataclass(frozen=True)
class LLMAnswer:
    model: str
    answer: str
    latency_ms: int
    error: str | None = None


class LLMClient(Protocol):
    model: str

    def answer(self, pergunta: str, sources: list[SearchResult]) -> LLMAnswer:
        """Gera resposta usando apenas as fontes recuperadas."""


def llm_client_from_spec(spec: str) -> LLMClient:
    provider, _, model = spec.partition(":")
    provider_key = provider.strip().lower()
    model_name = model.strip()
    if not model_name:
        raise ValueError("Use o formato provedor:modelo, por exemplo groq:llama-3.3-70b-versatile")
    if provider_key in OPENAI_COMPATIBLE_ENDPOINTS:
        env_key, endpoint = OPENAI_COMPATIBLE_ENDPOINTS[provider_key]
        return OpenAICompatibleChatClient(
            provider=provider_key,
            model=model_name,
            api_key_env=env_key,
            endpoint=endpoint,
        )
    if provider_key == "gemini":
        return GeminiChatClient(model=model_name)
    raise ValueError(f"Provedor de LLM desconhecido: {provider_key}")


class OpenAICompatibleChatClient:
    def __init__(
        self,
        provider: str,
        model: str,
        api_key_env: str,
        endpoint: str,
        timeout_seconds: float = 60.0,
    ) -> None:
        resolved_key = os.getenv(api_key_env)
        if not resolved_key:
            raise RuntimeError(f"Defina {api_key_env} para avaliar {provider}.")
        self.provider = provider
        self.model = f"{provider}:{model}"
        self.model_name = model
        self.api_key = resolved_key
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def answer(self, pergunta: str, sources: list[SearchResult]) -> LLMAnswer:
        started = time.perf_counter()
        try:
            response = httpx.post(
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model_name,
                    "temperature": 0.1,
                    "messages": [
                        {"role": "system", "content": _system_prompt()},
                        {"role": "user", "content": _user_prompt(pergunta, sources)},
                    ],
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            answer = payload["choices"][0]["message"]["content"].strip()
            return LLMAnswer(self.model, answer, _elapsed_ms(started))
        except Exception as exc:
            return LLMAnswer(self.model, "", _elapsed_ms(started), error=_safe_error(exc))


class GeminiChatClient:
    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        resolved_key = api_key or os.getenv("GEMINI_API_KEY")
        if not resolved_key:
            raise RuntimeError("Defina GEMINI_API_KEY para avaliar Gemini.")
        self.model = f"gemini:{model}"
        self.model_name = model
        self.api_key = resolved_key
        self.timeout_seconds = timeout_seconds

    def answer(self, pergunta: str, sources: list[SearchResult]) -> LLMAnswer:
        started = time.perf_counter()
        try:
            response = httpx.post(
                GEMINI_ENDPOINT_TEMPLATE.format(model=self.model_name),
                params={"key": self.api_key},
                headers={"Content-Type": "application/json"},
                json={
                    "systemInstruction": {"parts": [{"text": _system_prompt()}]},
                    "contents": [
                        {
                            "role": "user",
                            "parts": [{"text": _user_prompt(pergunta, sources)}],
                        }
                    ],
                    "generationConfig": {"temperature": 0.1},
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            answer = payload["candidates"][0]["content"]["parts"][0]["text"].strip()
            return LLMAnswer(self.model, answer, _elapsed_ms(started))
        except Exception as exc:
            return LLMAnswer(self.model, "", _elapsed_ms(started), error=_safe_error(exc))


GroqChatClient = OpenAICompatibleChatClient


def _system_prompt() -> str:
    return (
        "Voce ajuda um defensor publico a se preparar para audiencia. "
        "Responda exclusivamente com base nas fontes fornecidas. "
        "Cite paginas no formato [p. N]. "
        "Se as fontes nao sustentarem a resposta, diga que nao encontrou base suficiente."
    )


def _user_prompt(pergunta: str, sources: list[SearchResult]) -> str:
    source_blocks = []
    for index, source in enumerate(sources, start=1):
        source_blocks.append(
            "\n".join(
                [
                    f"Fonte {index}",
                    f"Pagina: {source.page_number}",
                    f"Trecho: {source.text}",
                ]
            )
        )
    return "\n\n".join(
        [
            f"Pergunta: {pergunta}",
            "Fontes recuperadas:",
            "\n\n".join(source_blocks) or "Nenhuma fonte recuperada.",
            "Responda em portugues do Brasil.",
        ]
    )


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _safe_error(exc: Exception) -> str:
    message = str(exc)
    message = re.sub(r"([?&]key=)[^&\\s]+", r"\1[REDACTED]", message)
    for env_name in ["GROQ_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "DEEPSEEK_API_KEY"]:
        secret = os.getenv(env_name)
        if secret:
            message = message.replace(secret, "[REDACTED]")
    return message
