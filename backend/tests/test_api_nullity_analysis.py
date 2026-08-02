import fitz
from fastapi.testclient import TestClient

from preparador_audiencia.legal_catalog import load_legal_topic
from preparador_audiencia.main import app
from preparador_audiencia.nullity_analysis import (
    NullityAnalysisResult,
    RequirementAssessment,
)
from preparador_audiencia.search import SearchResult


def _pdf_bytes() -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Reconhecimento fotografico na pagina 1.")
    payload = document.tobytes()
    document.close()
    return payload


def test_recognition_nullity_endpoint_returns_structured_diagnosis(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PREPARADOR_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("PREPARADOR_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("PREPARADOR_CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("PREPARADOR_EMBEDDING_PROVIDER", "hash")
    client = TestClient(app)
    upload = client.post(
        "/upload",
        files={"file": ("processo.pdf", _pdf_bytes(), "application/pdf")},
    )
    processo_id = upload.json()["processo_id"]
    topic = load_legal_topic("reconhecimento_pessoas")
    source = SearchResult(
        text="A vitima recebeu uma fotografia isolada.",
        page_number=1,
        chunk_index=0,
        document_type="termo_reconhecimento",
        score=0.9,
    )

    def fake_analysis(*args, **kwargs) -> NullityAnalysisResult:
        assert args[0] == processo_id
        assert kwargs["top_k"] == 16
        return NullityAnalysisResult(
            topic=topic.id,
            title=topic.title,
            conclusion="forte_fundamento_para_alegar_invalidade",
            conclusion_label="Forte fundamento para alegar invalidade do reconhecimento",
            confidence="alta",
            summary="Houve apresentacao fotografica isolada.",
            applicability="sim",
            applicability_summary="A pessoa era desconhecida.",
            procedural_impact="reconhecimento_determinante_sem_prova_independente",
            impact_summary="Nao foi localizada prova independente.",
            impact_pages=(1,),
            requirements=(
                RequirementAssessment(
                    id="procedimento_nao_sugestivo",
                    category="validade",
                    label="Procedimento nao sugestivo",
                    condition="Aplicavel.",
                    result="nao_observado",
                    justification="Foi exibida apenas uma fotografia.",
                    pages=(1,),
                    legal_source_ids=("stj_tema_1258",),
                ),
            ),
            next_steps=("Avaliar a arguicao defensiva.",),
            gaps=("Conferir o auto.",),
            model="gemini:test",
            fallback_used=False,
            process_sources=(source,),
            legal_sources=topic.sources,
            legal_catalog_version=topic.version,
            legal_catalog_verified_at=topic.verified_at,
            warnings=("Abra a pagina citada.",),
        )

    monkeypatch.setattr(
        "preparador_audiencia.api.analyze_recognition_nullity",
        fake_analysis,
    )

    response = client.post(
        f"/processo/{processo_id}/analise-nulidade/reconhecimento",
        json={"top_k": 16},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["conclusao"] == "forte_fundamento_para_alegar_invalidade"
    assert payload["requisitos"][0]["resultado"] == "nao_observado"
    assert payload["fontes_processuais"][0]["pagina"] == 1
    assert payload["paginas_impacto"] == [1]
    assert {source["id"] for source in payload["fontes_juridicas"]} >= {
        "cpp_arts_226_228",
        "stj_tema_1258",
    }
    assert payload["versao_catalogo_juridico"] == "2026.08.02"


def test_recognition_nullity_endpoint_rejects_invalid_top_k() -> None:
    client = TestClient(app)

    response = client.post(
        "/processo/proc_1/analise-nulidade/reconhecimento",
        json={"top_k": 21},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_top_k"
