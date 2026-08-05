from fastapi.testclient import TestClient

from preparador_audiencia.chunking import TextChunk
from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.legal_catalog import load_legal_topic
from preparador_audiencia.main import app
from preparador_audiencia.nullity_analysis_repository import (
    NullityAnalysisRepository,
)
from preparador_audiencia.procedural_nullity_engine import (
    ProceduralNullityUnavailableError,
)
from preparador_audiencia.repositories import ChunkRepository, ProcessoRepository


def _create_process(database_path, *, completed: bool = True) -> None:
    connection = connect_database(database_path)
    initialize_database(connection)
    processes = ProcessoRepository(connection)
    processes.create_pending("proc-1", "processo.pdf", "storage/processo.pdf", "abc")
    ChunkRepository(connection).replace_for_processo(
        "proc-1",
        [
            TextChunk(
                page_number=8,
                chunk_index=0,
                text="A substancia chegou sem lacre para pericia.",
            )
        ],
    )
    if completed:
        processes.mark_completed("proc-1", page_count=8, chunk_count=1)
    connection.close()


def _saved_record(processo_id, topic_id, repository, **_kwargs):
    topic = load_legal_topic(topic_id)
    return repository.save(
        processo_id,
        topic_id,
        catalog_version=topic.version,
        conclusion="indicios_suficientes",
        payload={
            "titulo": topic.title,
            "escopo": topic.scope,
            "conclusao_rotulo": "Indicios suficientes para aprofundar a arguicao",
            "confianca": "media",
            "resumo": "Falha documentada para revisao.",
            "requisitos": [],
            "providencias": ["Abrir a pagina citada."],
            "lacunas": [],
            "fontes_processuais": [],
            "fontes_juridicas": [
                {
                    "id": source.id,
                    "autoridade": source.authority,
                    "tipo": source.kind,
                    "titulo": source.title,
                    "referencia": source.reference,
                    "url": source.url,
                    "resumo": source.summary,
                }
                for source in topic.sources
            ],
            "avisos": ["Revisao necessaria."],
        },
        model="gemini:test",
        fallback_used=False,
        search_mode="hibrida",
    )


def test_single_topic_endpoint_generates_persists_and_loads(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(database_path))
    _create_process(database_path)
    monkeypatch.setattr(
        "preparador_audiencia.routes.procedural_nullities.generate_procedural_nullity",
        _saved_record,
    )
    client = TestClient(app)

    generated = client.post(
        "/processo/proc-1/analise-nulidades/cadeia_custodia",
        json={"top_k": 24, "regenerar": False},
    )
    loaded = client.get(
        "/processo/proc-1/analise-nulidades/cadeia_custodia"
    )

    assert generated.status_code == 200
    assert generated.json()["conclusao"] == "indicios_suficientes"
    assert generated.json()["versao_catalogo"] == "2026.08.04"
    assert loaded.status_code == 200
    assert loaded.json() == generated.json()


def test_batch_endpoint_persists_successes_when_one_provider_fails(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(database_path))
    _create_process(database_path)

    def generate(processo_id, topic_id, repository, **kwargs):
        if topic_id == "busca_pessoal_domiciliar":
            raise ProceduralNullityUnavailableError("provedores indisponiveis")
        return _saved_record(processo_id, topic_id, repository, **kwargs)

    monkeypatch.setattr(
        "preparador_audiencia.routes.procedural_nullities.generate_procedural_nullity",
        generate,
    )
    response = TestClient(app).post(
        "/processo/proc-1/analise-nulidades",
        json={
            "temas": ["cadeia_custodia", "busca_pessoal_domiciliar"],
            "top_k": 24,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "parcial"
    assert [item["tema"] for item in response.json()["analises"]] == [
        "cadeia_custodia"
    ]
    assert response.json()["erros"][0]["tema"] == "busca_pessoal_domiciliar"
    connection = connect_database(database_path)
    initialize_database(connection)
    assert NullityAnalysisRepository(connection).get("proc-1", "cadeia_custodia")
    connection.close()


def test_endpoint_rejects_unknown_topic_and_invalid_top_k() -> None:
    client = TestClient(app)

    unknown = client.post(
        "/processo/proc-1/analise-nulidades/tema_inexistente",
        json={"top_k": 24},
    )
    invalid_top_k = client.post(
        "/processo/proc-1/analise-nulidades/cadeia_custodia",
        json={"top_k": 5},
    )

    assert unknown.status_code == 400
    assert unknown.json()["error"] == "invalid_nullity_topic"
    assert invalid_top_k.status_code == 400
    assert invalid_top_k.json()["error"] == "invalid_top_k"


def test_endpoint_requires_completed_process(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(database_path))
    _create_process(database_path, completed=False)

    response = TestClient(app).post(
        "/processo/proc-1/analise-nulidades/cadeia_custodia",
        json={"top_k": 24},
    )

    assert response.status_code == 409
    assert response.json()["error"] == "process_not_ready"
