from fastapi.testclient import TestClient

from preparador_audiencia.chunking import TextChunk
from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.main import app
from preparador_audiencia.repositories import ChunkRepository, ProcessoRepository


def _process_with_testimony(database_path, *, completed: bool = True) -> None:
    connection = connect_database(database_path)
    initialize_database(connection)
    processes = ProcessoRepository(connection)
    processes.create_pending("proc_1", "processo.pdf", "storage/processo.pdf", "abc")
    text = (
        "TERMO DE DEPOIMENTO QUE PRESTA A TESTEMUNHA: MARIA LIMA\n"
        "INQUERITO 1\nDISSE QUE viu os fatos. Nada mais disse. Pag. 1 de 1"
    )
    ChunkRepository(connection).replace_for_processo(
        "proc_1",
        [TextChunk(page_number=7, chunk_index=0, text=text)],
    )
    if completed:
        processes.mark_completed("proc_1", page_count=7, chunk_count=1)
    connection.close()


def test_endpoint_generates_persists_and_loads_transcription(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(database_path))
    _process_with_testimony(database_path)
    client = TestClient(app)

    generated = client.post(
        "/processo/proc_1/transcricao-depoimentos",
        json={"regenerar": False},
    )
    loaded = client.get("/processo/proc_1/transcricao-depoimentos")

    assert generated.status_code == 200
    assert generated.json()["status"] == "concluido"
    assert generated.json()["depoimentos"][0]["pessoa"] == "MARIA LIMA"
    assert generated.json()["depoimentos"][0]["paginas"][0]["pagina"] == 7
    assert loaded.status_code == 200
    assert loaded.json() == generated.json()


def test_endpoint_requires_completed_process(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(database_path))
    _process_with_testimony(database_path, completed=False)

    response = TestClient(app).post(
        "/processo/proc_1/transcricao-depoimentos",
        json={"regenerar": False},
    )

    assert response.status_code == 409
    assert response.json()["error"] == "process_not_ready"


def test_get_returns_not_found_before_generation(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(database_path))
    _process_with_testimony(database_path)

    response = TestClient(app).get("/processo/proc_1/transcricao-depoimentos")

    assert response.status_code == 404
    assert response.json()["error"] == "transcription_not_found"
