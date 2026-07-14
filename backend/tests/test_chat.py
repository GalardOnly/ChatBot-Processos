from preparador_audiencia.chat import NO_SOURCES_ANSWER, answer_process_question
from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.llm import LLMAnswer
from preparador_audiencia.repositories import ChatMessageRepository, ProcessoRepository
from preparador_audiencia.search import SearchResult


class FakeLLMClient:
    def __init__(self, model: str, answer: LLMAnswer) -> None:
        self.model = model
        self._answer = answer

    def answer(self, pergunta: str, sources: list[SearchResult]) -> LLMAnswer:
        return self._answer


def create_chat_repository(tmp_path) -> ChatMessageRepository:
    connection = connect_database(tmp_path / "test.sqlite3")
    initialize_database(connection)
    ProcessoRepository(connection).create_pending(
        processo_id="proc_123",
        filename="processo.pdf",
        file_path="storage/processo.pdf",
        sha256_digest="abc",
    )
    return ChatMessageRepository(connection)


def fake_sources() -> list[SearchResult]:
    return [
        SearchResult(
            text="Audiencia de instrucao designada para 20/08/2026.",
            page_number=2,
            chunk_index=0,
            document_type="audiencia",
            score=0.91,
        )
    ]


def test_answer_process_question_uses_primary_model_and_records_history(
    tmp_path,
    monkeypatch,
) -> None:
    messages = create_chat_repository(tmp_path)
    monkeypatch.setattr("preparador_audiencia.chat.search_process", lambda **kwargs: fake_sources())
    monkeypatch.setattr(
        "preparador_audiencia.chat.llm_client_from_spec",
        lambda spec: FakeLLMClient(
            spec,
            LLMAnswer(
                model="gemini:gemini-flash-latest",
                answer="A audiencia foi designada para 20/08/2026 [p. 2].",
                latency_ms=123,
            ),
        ),
    )

    result = answer_process_question(
        "proc_123",
        "Quando sera a audiencia?",
        messages,
        primary_model="gemini:gemini-flash-latest",
        fallback_model="groq:llama-3.1-8b-instant",
    )

    history = messages.list_for_processo("proc_123")
    assert result.modelo == "gemini:gemini-flash-latest"
    assert result.fallback_usado is False
    assert result.fontes[0].page_number == 2
    assert history[0].role == "user"
    assert history[1].role == "assistant"
    assert history[1].model == "gemini:gemini-flash-latest"
    assert history[1].retrieved_pages == [2]
    assert history[1].retrieved_chunks[0]["chunk_index"] == 0


def test_answer_process_question_uses_groq_fallback_when_primary_fails(
    tmp_path,
    monkeypatch,
) -> None:
    messages = create_chat_repository(tmp_path)
    calls: list[str] = []

    def fake_client(spec: str) -> FakeLLMClient:
        calls.append(spec)
        if spec.startswith("gemini:"):
            return FakeLLMClient(
                spec,
                LLMAnswer(model=spec, answer="", latency_ms=10, error="timeout"),
            )
        return FakeLLMClient(
            spec,
            LLMAnswer(
                model="groq:llama-3.1-8b-instant",
                answer="Ha audiencia designada no processo [p. 2].",
                latency_ms=50,
            ),
        )

    monkeypatch.setattr("preparador_audiencia.chat.search_process", lambda **kwargs: fake_sources())
    monkeypatch.setattr("preparador_audiencia.chat.llm_client_from_spec", fake_client)

    result = answer_process_question(
        "proc_123",
        "Existe audiencia?",
        messages,
        primary_model="gemini:gemini-flash-latest",
        fallback_model="groq:llama-3.1-8b-instant",
    )

    history = messages.list_for_processo("proc_123")
    assert calls == ["gemini:gemini-flash-latest", "groq:llama-3.1-8b-instant"]
    assert result.modelo == "groq:llama-3.1-8b-instant"
    assert result.fallback_usado is True
    assert history[1].model == "groq:llama-3.1-8b-instant"


def test_answer_process_question_does_not_call_llm_without_sources(tmp_path, monkeypatch) -> None:
    messages = create_chat_repository(tmp_path)
    monkeypatch.setattr("preparador_audiencia.chat.search_process", lambda **kwargs: [])

    def fail_if_called(spec: str) -> FakeLLMClient:
        raise AssertionError(f"LLM nao deveria ser chamado: {spec}")

    monkeypatch.setattr("preparador_audiencia.chat.llm_client_from_spec", fail_if_called)

    result = answer_process_question("proc_123", "Qual foi a decisao?", messages)

    history = messages.list_for_processo("proc_123")
    assert result.resposta == NO_SOURCES_ANSWER
    assert result.modelo == "sistema"
    assert result.fontes == []
    assert history[1].content == NO_SOURCES_ANSWER
    assert history[1].model == "sistema"
