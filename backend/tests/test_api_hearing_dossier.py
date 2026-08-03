from fastapi.testclient import TestClient

from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.main import app
from preparador_audiencia.repositories import ProcessoRepository


def _completed_process(database_path) -> None:
    connection = connect_database(database_path)
    initialize_database(connection)
    processes = ProcessoRepository(connection)
    processes.create_pending("proc_1", "processo.pdf", "storage/processo.pdf", "abc")
    processes.mark_completed("proc_1", page_count=10, chunk_count=20)
    connection.close()


def test_dossier_endpoint_persists_structured_response(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(database_path))
    _completed_process(database_path)

    def fake_generation(processo_id, repository, **kwargs):
        repository.prepare(processo_id)
        repository.save_section(
            processo_id,
            "marcos_essenciais",
            {
                "itens": [
                    {
                        "tipo": "data_fato",
                        "rotulo": "Data do fato",
                        "valor": "12/03/2018",
                        "pessoa": None,
                        "descricao": None,
                        "fontes": [
                            {
                                "pagina": 14,
                                "chunk_index": 0,
                                "tipo_documento": "denuncia",
                                "confianca_fonte": "alta",
                                "trecho": "O fato ocorreu em 12/03/2018.",
                            }
                        ],
                    }
                ],
                "campos_para_confirmar": [],
                "avisos": [],
            },
            model="gemini:test",
            fallback_used=False,
        )
        repository.save_section(
            processo_id,
            "depoimentos",
            {"itens": [], "lacunas": [], "avisos": []},
            model="gemini:test",
            fallback_used=False,
        )
        repository.save_section(
            processo_id,
            "contradicoes",
            {"itens": [], "lacunas": [], "avisos": []},
            model="gemini:test",
            fallback_used=False,
        )
        return repository.finish(processo_id)

    monkeypatch.setattr(
        "preparador_audiencia.routes.hearing_dossier.generate_hearing_dossier",
        fake_generation,
    )
    client = TestClient(app)

    generated = client.post(
        "/processo/proc_1/dossie-audiencia",
        json={"top_k": 18},
    )
    loaded = client.get("/processo/proc_1/dossie-audiencia")

    assert generated.status_code == 200
    assert generated.json()["status"] == "concluido"
    assert generated.json()["marcos_essenciais"]["itens"][0]["fontes"][0][
        "pagina"
    ] == 14
    assert loaded.status_code == 200
    assert loaded.json() == generated.json()


def test_dossier_endpoint_requires_completed_process(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(database_path))
    connection = connect_database(database_path)
    initialize_database(connection)
    ProcessoRepository(connection).create_pending(
        "proc_1",
        "processo.pdf",
        "storage/processo.pdf",
        "abc",
    )
    connection.close()

    response = TestClient(app).post(
        "/processo/proc_1/dossie-audiencia",
        json={"top_k": 18},
    )

    assert response.status_code == 409
    assert response.json()["error"] == "process_not_ready"


def test_get_dossier_returns_not_found_before_generation(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(database_path))
    _completed_process(database_path)

    response = TestClient(app).get("/processo/proc_1/dossie-audiencia")

    assert response.status_code == 404
    assert response.json()["error"] == "dossier_not_found"


def test_dossier_endpoint_returns_503_when_all_sections_fail(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(database_path))
    _completed_process(database_path)

    def fake_failure(processo_id, repository, **kwargs):
        repository.prepare(processo_id)
        for section_key in ("marcos_essenciais", "depoimentos", "contradicoes"):
            repository.mark_section_error(
                processo_id,
                section_key,
                "Gemini e Groq indisponiveis.",
            )
        return repository.finish(processo_id)

    monkeypatch.setattr(
        "preparador_audiencia.routes.hearing_dossier.generate_hearing_dossier",
        fake_failure,
    )

    response = TestClient(app).post(
        "/processo/proc_1/dossie-audiencia",
        json={"top_k": 18},
    )

    assert response.status_code == 503
    assert response.json()["error"] == "llm_unavailable"
    saved = TestClient(app).get("/processo/proc_1/dossie-audiencia")
    assert saved.status_code == 200
    assert saved.json()["status"] == "erro"
