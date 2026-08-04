from fastapi.testclient import TestClient

from preparador_audiencia.chunking import TextChunk
from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.judgment_structure_repository import (
    JudgmentStructureRepository,
)
from preparador_audiencia.main import app
from preparador_audiencia.repositories import ChunkRepository, ProcessoRepository


def _process_with_sentence(database_path, *, completed: bool = True) -> None:
    connection = connect_database(database_path)
    initialize_database(connection)
    processes = ProcessoRepository(connection)
    processes.create_pending("proc-1", "processo.pdf", "storage/processo.pdf", "abc")
    ChunkRepository(connection).replace_for_processo(
        "proc-1",
        [
            TextChunk(page_number=20, chunk_index=0, text="SENTENCA\nRelatorio."),
            TextChunk(
                page_number=21,
                chunk_index=0,
                text=(
                    "Diante do exposto, CONDENO o reu no art. 155 do Codigo Penal. "
                    "Pena definitiva em 2 anos de reclusao. Regime inicial aberto."
                ),
            ),
            TextChunk(
                page_number=22,
                chunk_index=0,
                text=(
                    "CERTIDAO DE TRANSITO EM JULGADO. Certifico que transitou em "
                    "julgado para ambas as partes em 15/06/2025."
                ),
            ),
        ],
    )
    if completed:
        processes.mark_completed("proc-1", page_count=22, chunk_count=3)
    connection.close()


def test_endpoint_generates_persists_and_loads_structure(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(database_path))
    _process_with_sentence(database_path)
    client = TestClient(app)

    generated = client.post(
        "/processo/proc-1/estrutura-sentenca",
        json={"regenerar": False},
    )
    loaded = client.get("/processo/proc-1/estrutura-sentenca")

    assert generated.status_code == 200
    body = generated.json()
    assert body["status"] == "concluido"
    assert body["decisoes"][0]["resultado"] == "condenatoria"
    assert body["decisoes"][0]["penas_aplicadas"][0]["anos"] == 2
    assert body["transitos_em_julgado"][0]["escopo"] == "ambas_partes"
    assert loaded.status_code == 200
    assert loaded.json() == body


def test_endpoint_requires_completed_process(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(database_path))
    _process_with_sentence(database_path, completed=False)

    response = TestClient(app).post(
        "/processo/proc-1/estrutura-sentenca",
        json={"regenerar": False},
    )

    assert response.status_code == 409
    assert response.json()["error"] == "process_not_ready"


def test_replacing_chunks_removes_saved_structure(tmp_path) -> None:
    database_path = tmp_path / "test.sqlite3"
    _process_with_sentence(database_path)
    connection = connect_database(database_path)
    repository = JudgmentStructureRepository(connection)
    saved = repository.save(
        "proc-1",
        status="nao_localizada",
        payload={"decisoes": [], "transitos_em_julgado": [], "avisos": []},
    )
    assert saved.processo_id == "proc-1"

    ChunkRepository(connection).replace_for_processo(
        "proc-1",
        [TextChunk(page_number=1, chunk_index=0, text="novo texto")],
    )

    assert repository.get("proc-1") is None
    connection.close()
