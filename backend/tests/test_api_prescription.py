from fastapi.testclient import TestClient

from preparador_audiencia.chunking import TextChunk
from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.main import app
from preparador_audiencia.repositories import ChunkRepository, ProcessoRepository


def _process_with_dates(database_path, *, completed: bool = True) -> None:
    connection = connect_database(database_path)
    initialize_database(connection)
    processes = ProcessoRepository(connection)
    processes.create_pending("proc-1", "processo.pdf", "storage/processo.pdf", "abc")
    chunks = [
        TextChunk(
            page_number=7,
            chunk_index=0,
            text=(
                "O fato ocorreu em 10/01/2020. A denuncia foi recebida em "
                "15/03/2020. O reu, nascido em 02/01/1990, foi qualificado."
            ),
        ),
        TextChunk(
            page_number=8,
            chunk_index=0,
            text="Art. 155. Pena - reclusao, de 1 (um) a 4 (quatro) anos.",
        ),
    ]
    ChunkRepository(connection).replace_for_processo("proc-1", chunks)
    if completed:
        processes.mark_completed("proc-1", page_count=8, chunk_count=2)
    connection.close()


def _request_payload() -> dict[str, object]:
    return {
        "data_referencia": "2026-08-03",
        "reu": "Pessoa testada",
        "data_nascimento_reu": "1990-01-02",
        "situacao_sentenca": "nao_proferida",
        "data_sentenca_condenatoria": None,
        "delitos": [
            {
                "id": "delito-1",
                "descricao": "Furto",
                "artigo": "Art. 155 do CP",
                "pena_maxima_meses": 48,
                "tipo_termo_inicial": "consumacao",
                "data_termo_inicial": "2020-01-10",
                "data_fato": "2020-01-10",
                "violencia_sexual_contra_mulher": False,
                "marcos_interruptivos": [
                    {
                        "tipo": "recebimento_denuncia",
                        "data": "2020-03-15",
                        "pagina": 7,
                        "trecho": "A denuncia foi recebida em 15/03/2020.",
                    }
                ],
                "periodos_suspensao": [],
            }
        ],
    }


def test_data_endpoint_returns_reviewable_candidates(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(database_path))
    _process_with_dates(database_path)

    response = TestClient(app).get("/processo/proc-1/prescricao/dados")

    assert response.status_code == 200
    body = response.json()
    by_type = {item["tipo_evento"]: item for item in body["datas"]}
    assert by_type["data_fato"]["data"] == "2020-01-10"
    assert by_type["recebimento_denuncia"]["data"] == "2020-03-15"
    assert by_type["recebimento_denuncia"]["pagina"] == 7
    assert by_type["recebimento_denuncia"]["revisao_necessaria"] is True
    assert body["delitos"][0]["pena_maxima_meses"] == 48


def test_calculation_endpoint_persists_and_reloads_result(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(database_path))
    _process_with_dates(database_path)
    client = TestClient(app)

    generated = client.post(
        "/processo/proc-1/prescricao/calcular",
        json=_request_payload(),
    )
    assert generated.status_code == 200
    body = generated.json()
    assert body["status"] == "prazos_nao_esgotados_no_calculo"
    assert body["delitos"][0]["prazo_base_meses"] == 96
    assert body["delitos"][0]["prazo_final"] == "2028-03-14"
    assert body["delitos"][0]["intervalos"][0]["status"] == (
        "interrompido_em_tempo"
    )
    assert body["fontes_juridicas"][0]["url"].startswith("https://www.planalto.gov.br")

    loaded = client.get(
        f"/processo/proc-1/prescricao/calculos/{body['calculo_id']}"
    )
    repeated = client.post(
        "/processo/proc-1/prescricao/calcular",
        json=_request_payload(),
    )

    assert loaded.status_code == 200
    assert loaded.json() == body
    assert repeated.status_code == 200
    assert repeated.json()["calculo_id"] == body["calculo_id"]


def test_missing_birth_date_returns_auditable_inconclusive_result(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(database_path))
    _process_with_dates(database_path)
    payload = _request_payload()
    payload["data_nascimento_reu"] = None

    response = TestClient(app).post(
        "/processo/proc-1/prescricao/calcular",
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "inconclusivo"
    assert "nascimento" in response.json()["delitos"][0]["campos_ausentes"][0]


def test_invalid_chronology_returns_controlled_error(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(database_path))
    _process_with_dates(database_path)
    payload = _request_payload()
    payload["delitos"][0]["marcos_interruptivos"][0]["data"] = "2019-01-01"

    response = TestClient(app).post(
        "/processo/proc-1/prescricao/calcular",
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_prescription_data"


def test_prescription_requires_completed_process(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(database_path))
    _process_with_dates(database_path, completed=False)

    response = TestClient(app).get("/processo/proc-1/prescricao/dados")

    assert response.status_code == 409
    assert response.json()["error"] == "process_not_ready"
