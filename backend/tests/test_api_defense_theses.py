import json

from fastapi.testclient import TestClient

from preparador_audiencia.chunking import TextChunk
from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.llm import LLMAnswer
from preparador_audiencia.main import app
from preparador_audiencia.repositories import ChunkRepository, ProcessoRepository
from preparador_audiencia.search import SearchResult


class _FakeClient:
    def complete(self, system_prompt: str, user_prompt: str) -> LLMAnswer:
        return LLMAnswer(
            "gemini:test",
            json.dumps(
                {
                    "teses": [
                        {
                            "catalogo_id": "duvida_autoria",
                            "analise": "A identificacao precisa ser confrontada.",
                            "prioridade": 1,
                            "fontes_favoraveis": [
                                {
                                    "fonte_id": "fonte-p10-c0",
                                    "trecho_exato": "nao conseguiu reconhecer o autor",
                                }
                            ],
                            "fontes_contrarias": [],
                            "pontos_para_confirmar": [
                                "Condicoes do reconhecimento."
                            ],
                        }
                    ],
                    "lacunas_gerais": [],
                }
            ),
            10,
        )


def _process(database_path, *, completed: bool = True) -> None:
    connection = connect_database(database_path)
    initialize_database(connection)
    processes = ProcessoRepository(connection)
    processes.create_pending("proc-1", "processo.pdf", "storage/processo.pdf", "abc")
    ChunkRepository(connection).replace_for_processo(
        "proc-1",
        [
            TextChunk(
                page_number=10,
                chunk_index=0,
                text="A vitima nao conseguiu reconhecer o autor na delegacia.",
            )
        ],
    )
    if completed:
        processes.mark_completed("proc-1", page_count=10, chunk_count=1)
    connection.close()


def test_endpoint_generates_persists_and_loads_theses(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(database_path))
    _process(database_path)
    monkeypatch.setattr(
        "preparador_audiencia.defense_theses.search_process_queries_configured",
        lambda **_kwargs: [
            SearchResult(
                text="A vitima nao conseguiu reconhecer o autor na delegacia.",
                page_number=10,
                chunk_index=0,
                document_type=None,
                score=0.9,
                source_confidence="alta",
            )
        ],
    )
    monkeypatch.setattr(
        "preparador_audiencia.defense_theses.llm_client_from_spec",
        lambda _spec: _FakeClient(),
    )
    client = TestClient(app)

    generated = client.post(
        "/processo/proc-1/teses-defensivas",
        json={"top_k": 20, "max_teses": 8, "regenerar": False},
    )
    loaded = client.get("/processo/proc-1/teses-defensivas")

    assert generated.status_code == 200
    body = generated.json()
    assert body["status"] == "concluido"
    assert body["teses"][0]["catalogo_id"] == "duvida_autoria"
    assert body["teses"][0]["fontes_favoraveis"][0]["paginas"] == [10]
    assert loaded.status_code == 200
    assert loaded.json() == body


def test_endpoint_validates_limits(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(database_path))
    _process(database_path)

    response = TestClient(app).post(
        "/processo/proc-1/teses-defensivas",
        json={"top_k": 5, "max_teses": 8, "regenerar": False},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_top_k"


def test_endpoint_requires_completed_process(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(database_path))
    _process(database_path, completed=False)

    response = TestClient(app).post(
        "/processo/proc-1/teses-defensivas",
        json={"top_k": 20, "max_teses": 8, "regenerar": False},
    )

    assert response.status_code == 409
    assert response.json()["error"] == "process_not_ready"
