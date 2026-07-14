import fitz
from fastapi.testclient import TestClient

from preparador_audiencia.chat import ChatResult
from preparador_audiencia.main import app
from preparador_audiencia.search import SearchResult


def create_pdf_bytes() -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Processo de teste\nAudiencia em 20/08/2026.")
    payload = document.tobytes()
    document.close()
    return payload


def test_upload_processes_pdf_and_status_returns_completed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("PREPARADOR_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("PREPARADOR_CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("PREPARADOR_EMBEDDING_PROVIDER", "hash")
    client = TestClient(app)

    response = client.post(
        "/upload",
        files={"file": ("processo.pdf", create_pdf_bytes(), "application/pdf")},
    )

    assert response.status_code == 200
    processo_id = response.json()["processo_id"]
    status = client.get(f"/processo/{processo_id}/status")
    assert status.status_code == 200
    assert status.json()["status"] == "concluido"
    assert status.json()["paginas_extraidas"] == 1
    assert status.json()["chunks"] == 1

    search = client.post(
        f"/processo/{processo_id}/buscar",
        json={"pergunta": "Quando sera a audiencia?", "top_k": 1},
    )
    assert search.status_code == 200
    assert search.json()["fontes"][0]["pagina"] == 1
    assert "Audiencia" in search.json()["fontes"][0]["trecho"]


def test_upload_rejects_non_pdf_payload(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("PREPARADOR_STORAGE_DIR", str(tmp_path / "storage"))
    client = TestClient(app)

    response = client.post(
        "/upload",
        files={"file": ("processo.txt", b"texto", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_file_type"


def test_status_returns_404_for_unknown_process(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    client = TestClient(app)

    response = client.get("/processo/proc_inexistente/status")

    assert response.status_code == 404
    assert response.json()["error"] == "process_not_found"


def test_search_returns_404_for_unknown_process(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("PREPARADOR_CHROMA_DIR", str(tmp_path / "chroma"))
    client = TestClient(app)

    response = client.post(
        "/processo/proc_inexistente/buscar",
        json={"pergunta": "Existe audiencia?", "top_k": 1},
    )

    assert response.status_code == 404
    assert response.json()["error"] == "process_not_found"


def test_chat_endpoint_returns_answer_with_sources(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("PREPARADOR_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("PREPARADOR_CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("PREPARADOR_EMBEDDING_PROVIDER", "hash")
    client = TestClient(app)

    upload = client.post(
        "/upload",
        files={"file": ("processo.pdf", create_pdf_bytes(), "application/pdf")},
    )
    processo_id = upload.json()["processo_id"]
    source = SearchResult(
        text="Audiencia em 20/08/2026.",
        page_number=1,
        chunk_index=0,
        document_type="audiencia",
        score=0.88,
    )

    def fake_answer_process_question(**kwargs) -> ChatResult:
        return ChatResult(
            pergunta=kwargs["pergunta"],
            resposta="A audiencia esta marcada para 20/08/2026 [p. 1].",
            modelo="gemini:gemini-flash-latest",
            fallback_usado=False,
            fontes=[source],
        )

    monkeypatch.setattr(
        "preparador_audiencia.api.answer_process_question",
        fake_answer_process_question,
    )

    response = client.post(
        f"/processo/{processo_id}/chat",
        json={"pergunta": "Quando sera a audiencia?", "top_k": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["modelo"] == "gemini:gemini-flash-latest"
    assert payload["fallback_usado"] is False
    assert payload["fontes"][0]["pagina"] == 1


def test_chat_returns_404_for_unknown_process(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    client = TestClient(app)

    response = client.post(
        "/processo/proc_inexistente/chat",
        json={"pergunta": "Existe audiencia?", "top_k": 1},
    )

    assert response.status_code == 404
    assert response.json()["error"] == "process_not_found"
