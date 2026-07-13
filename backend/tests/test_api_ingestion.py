import fitz
from fastapi.testclient import TestClient

from preparador_audiencia.main import app


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

