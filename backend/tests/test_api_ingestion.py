from inspect import iscoroutinefunction

import fitz
from fastapi.testclient import TestClient

from preparador_audiencia.chat import ChatResult
from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.main import app
from preparador_audiencia.quality import LegalQualityEvaluation
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
    assert status.json()["etapa"] == "concluido"
    assert status.json()["progresso_percentual"] == 100
    assert status.json()["consulta_disponivel"] is True
    assert status.json()["modo_busca"] == "hibrida"

    search = client.post(
        f"/processo/{processo_id}/buscar",
        json={"pergunta": "Quando sera a audiencia?", "top_k": 1},
    )
    assert search.status_code == 200
    assert search.json()["modo_busca"] == "hibrida"
    assert search.json()["fontes"][0]["pagina"] == 1
    assert "Audiencia" in search.json()["fontes"][0]["trecho"]


def test_upload_reuses_identical_completed_pdf(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("PREPARADOR_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("PREPARADOR_CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("PREPARADOR_EMBEDDING_PROVIDER", "hash")
    client = TestClient(app)
    payload = create_pdf_bytes()

    first = client.post(
        "/upload",
        files={"file": ("processo.pdf", payload, "application/pdf")},
    )
    second = client.post(
        "/upload",
        files={"file": ("copia-do-processo.pdf", payload, "application/pdf")},
    )

    assert second.status_code == 200
    assert second.json()["processo_id"] == first.json()["processo_id"]
    assert second.json()["status"] == "concluido"
    assert second.json()["reutilizado"] is True
    assert len(list((tmp_path / "storage").glob("*.pdf"))) == 1


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


def test_upload_rejects_pdf_above_configured_limit(tmp_path, monkeypatch) -> None:
    storage_dir = tmp_path / "storage"
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("PREPARADOR_STORAGE_DIR", str(storage_dir))
    monkeypatch.setenv("PREPARADOR_MAX_UPLOAD_MB", "1")
    client = TestClient(app)
    oversized_pdf = b"%PDF-1.7\n" + (b"0" * (1024 * 1024))

    response = client.post(
        "/upload",
        files={"file": ("grande.pdf", oversized_pdf, "application/pdf")},
    )

    assert response.status_code == 413
    assert response.json()["error"] == "file_too_large"
    assert not list(storage_dir.glob("*"))


def test_status_returns_404_for_unknown_process(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    client = TestClient(app)

    response = client.get("/processo/proc_inexistente/status")

    assert response.status_code == 404
    assert response.json()["error"] == "process_not_found"


def test_status_marks_legacy_process_and_allows_reprocessing(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("PREPARADOR_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("PREPARADOR_CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("PREPARADOR_EMBEDDING_PROVIDER", "hash")
    client = TestClient(app)
    upload = client.post(
        "/upload",
        files={"file": ("processo.pdf", create_pdf_bytes(), "application/pdf")},
    )
    processo_id = upload.json()["processo_id"]
    connection = connect_database(database_path)
    initialize_database(connection)
    connection.execute(
        "UPDATE chunks SET source_confidence = 'desconhecida' WHERE processo_id = ?",
        (processo_id,),
    )
    connection.commit()
    processed: list[str] = []
    monkeypatch.setattr(
        "preparador_audiencia.api.process_pdf",
        lambda current_id: processed.append(current_id),
    )

    status = client.get(f"/processo/{processo_id}/status")
    reprocess = client.post(f"/processo/{processo_id}/reprocessar")

    assert status.json()["reprocessamento_necessario"] is True
    assert reprocess.status_code == 200
    assert reprocess.json()["status"] == "pendente"
    assert processed == [processo_id]


def test_list_recent_processes_returns_uploaded_process(tmp_path, monkeypatch) -> None:
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

    response = client.get("/processos?limit=1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["processos"][0]["processo_id"] == processo_id
    assert payload["processos"][0]["paginas_extraidas"] == 1
    assert payload["processos"][0]["chunks"] == 1


def test_list_hearing_questions_returns_filtered_templates() -> None:
    client = TestClient(app)

    response = client.get("/perguntas-audiencia?area=criminal&tag=custodia&limit=2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["perguntas"]
    assert all(item["area"] == "criminal" for item in payload["perguntas"])
    assert all("custodia" in item["tags"] for item in payload["perguntas"])


def test_list_hearing_questions_rejects_invalid_limit() -> None:
    client = TestClient(app)

    response = client.get("/perguntas-audiencia?limit=101")

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_limit"


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


def test_status_search_and_chat_use_lexical_mode_during_semantic_indexing(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("PREPARADOR_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("PREPARADOR_CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("PREPARADOR_EMBEDDING_PROVIDER", "hash")
    client = TestClient(app)
    upload = client.post(
        "/upload",
        files={"file": ("processo.pdf", create_pdf_bytes(), "application/pdf")},
    )
    processo_id = upload.json()["processo_id"]
    connection = connect_database(database_path)
    initialize_database(connection)
    connection.execute(
        """
        UPDATE processos
        SET status = 'processando', progress_stage = 'indexando'
        WHERE id = ?
        """,
        (processo_id,),
    )
    connection.commit()
    connection.close()
    lexical_flags: list[bool] = []

    def fake_answer_process_question(**kwargs) -> ChatResult:
        lexical_flags.append(kwargs["lexical_only"])
        return ChatResult(
            pergunta=kwargs["pergunta"],
            resposta="A audiencia esta marcada para 20/08/2026 [p. 1].",
            modelo="gemini:gemini-3-flash-preview",
            fallback_usado=False,
            fontes=[],
        )

    monkeypatch.setattr(
        "preparador_audiencia.api.answer_process_question",
        fake_answer_process_question,
    )

    status = client.get(f"/processo/{processo_id}/status")
    search = client.post(
        f"/processo/{processo_id}/buscar",
        json={"pergunta": "Quando sera a audiencia?", "top_k": 1},
    )
    chat = client.post(
        f"/processo/{processo_id}/chat",
        json={"pergunta": "Quando sera a audiencia?", "top_k": 1},
    )

    assert status.status_code == 200
    assert status.json()["consulta_disponivel"] is True
    assert status.json()["modo_busca"] == "lexical"
    assert search.status_code == 200
    assert search.json()["modo_busca"] == "lexical"
    assert search.json()["fontes"][0]["pagina"] == 1
    assert chat.status_code == 200
    assert chat.json()["modo_busca"] == "lexical"
    assert lexical_flags == [True]


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
            modelo="gemini:gemini-3-flash-preview",
            fallback_usado=False,
            fontes=[source],
            avaliacao=LegalQualityEvaluation(
                evaluator_model="groq:judge",
                fidelidade_fontes=5,
                completude_juridica=4,
                utilidade_audiencia=4,
                risco_alucinacao="baixo",
                pontos_fortes=["cita pagina"],
                problemas=[],
                faltou=[],
                veredito="Boa resposta para triagem.",
                raw_response="{}",
            )
            if kwargs["evaluate_quality"]
            else None,
        )

    monkeypatch.setattr(
        "preparador_audiencia.api.answer_process_question",
        fake_answer_process_question,
    )

    response = client.post(
        f"/processo/{processo_id}/chat",
        json={"pergunta": "Quando sera a audiencia?", "top_k": 1, "avaliar": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["modelo"] == "gemini:gemini-3-flash-preview"
    assert payload["fallback_usado"] is False
    assert payload["modo_busca"] == "hibrida"
    assert payload["fontes"][0]["pagina"] == 1
    assert payload["avaliacao"]["modelo_avaliador"] == "groq:judge"
    assert payload["avaliacao"]["fidelidade_fontes"] == 5


def test_chat_returns_404_for_unknown_process(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    client = TestClient(app)

    response = client.post(
        "/processo/proc_inexistente/chat",
        json={"pergunta": "Existe audiencia?", "top_k": 1},
    )

    assert response.status_code == 404
    assert response.json()["error"] == "process_not_found"


def test_blocking_api_routes_run_in_fastapi_threadpool() -> None:
    blocking_paths = {
        "/processo/{processo_id}/status",
        "/processo/{processo_id}/reprocessar",
        "/processos",
        "/perguntas-audiencia",
        "/processo/{processo_id}/buscar",
        "/processo/{processo_id}/chat",
    }
    endpoints = {
        route.path: route.endpoint
        for route in app.routes
        if getattr(route, "path", None) in blocking_paths
    }

    assert endpoints.keys() == blocking_paths
    assert all(not iscoroutinefunction(endpoint) for endpoint in endpoints.values())
