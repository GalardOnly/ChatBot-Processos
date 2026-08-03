import json

from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.hearing_dossier import (
    SectionGenerationResult,
    _retrieve_diverse_sources,
    generate_dossier_section,
    generate_hearing_dossier,
)
from preparador_audiencia.hearing_dossier_repository import HearingDossierRepository
from preparador_audiencia.llm import LLMAnswer
from preparador_audiencia.repositories import ProcessoRepository
from preparador_audiencia.search import SearchResult


class FakeClient:
    def __init__(self, answer: LLMAnswer) -> None:
        self.answer = answer
        self.prompts: list[tuple[str, str]] = []

    def complete(self, system_prompt: str, user_prompt: str) -> LLMAnswer:
        self.prompts.append((system_prompt, user_prompt))
        return self.answer


def _source(
    text: str,
    *,
    page: int,
    chunk: int = 0,
    confidence: str = "alta",
) -> SearchResult:
    return SearchResult(
        text=text,
        page_number=page,
        chunk_index=chunk,
        document_type="termo_declaracoes",
        score=0.9,
        source_confidence=confidence,
    )


def test_key_events_only_accept_pages_from_retrieved_sources(monkeypatch) -> None:
    source = _source(
        "O fato ocorreu em 12/03/2018, as 20h. A denuncia foi recebida em 20/09/2018.",
        page=14,
    )
    monkeypatch.setattr(
        "preparador_audiencia.hearing_dossier.search_process_queries_configured",
        lambda **kwargs: [source],
    )
    payload = json.dumps(
        {
            "itens": [
                {
                    "tipo": "data_fato",
                    "rotulo": "Data do fato",
                    "valor": "12/03/2018, as 20h",
                    "pessoa": "",
                    "descricao": "Data descrita no relato.",
                    "fonte_ids": ["P1", "P999"],
                },
                {
                    "tipo": "recebimento_denuncia",
                    "rotulo": "Recebimento da denuncia",
                    "valor": "20/09/2099",
                    "fonte_ids": ["P1"],
                },
                {
                    "tipo": "nascimento_reu",
                    "rotulo": "Nascimento",
                    "valor": "01/01/1990",
                    "fonte_ids": ["P999"],
                },
                {
                    "tipo": "suspensao_inicio",
                    "rotulo": "Inicio da suspensao",
                    "valor": "20/09/2018",
                    "fonte_ids": ["P1"],
                },
            ],
            "lacunas": [
                "data_fato",
                "recebimento_denuncia",
                "Informacao complementar",
            ],
        }
    )
    client = FakeClient(LLMAnswer("gemini:test", payload, 4))
    monkeypatch.setattr(
        "preparador_audiencia.hearing_dossier.llm_client_from_spec",
        lambda spec: client,
    )

    result = generate_dossier_section(
        "proc_1",
        "marcos_essenciais",
        primary_model="gemini:test",
        fallback_model="groq:test",
    )

    assert len(result.payload["itens"]) == 1
    event = result.payload["itens"][0]
    assert event["fontes"][0]["pagina"] == 14
    missing = {item["campo"] for item in result.payload["campos_para_confirmar"]}
    assert "nascimento_reu" in missing
    assert "recebimento_denuncia" in missing
    assert not any(
        item["tipo"].startswith("suspensao") for item in result.payload["itens"]
    )
    assert sum(
        item["campo"] == "recebimento_denuncia"
        for item in result.payload["campos_para_confirmar"]
    ) == 1
    assert any(
        item["rotulo"] == "Informacao complementar"
        for item in result.payload["campos_para_confirmar"]
    )
    assert "P999" not in json.dumps(result.payload)


def test_testimony_discards_invented_quote_and_downgrades_unproven_integral(
    monkeypatch,
) -> None:
    sources = [
        _source("A vitima declarou que viu apenas o nariz do autor.", page=21, chunk=0),
        _source("Depois afirmou que nao poderia reconhecer a pessoa.", page=23, chunk=0),
    ]
    monkeypatch.setattr(
        "preparador_audiencia.hearing_dossier.search_process_queries_configured",
        lambda **kwargs: sources,
    )
    payload = json.dumps(
        {
            "itens": [
                {
                    "pessoa": "Vitima",
                    "papel": "v\u00edtima",
                    "fase": "inquerito",
                    "cobertura": "integral",
                    "inicio_localizado": True,
                    "fim_localizado": True,
                    "trechos": [
                        {
                            "trecho_exato": "declarou que viu apenas o nariz do autor.",
                            "fonte_id": "P1",
                        },
                        {
                            "trecho_exato": "frase que nao existe no processo",
                            "fonte_id": "P2",
                        },
                        {
                            "trecho_exato": "nariz",
                            "fonte_id": "P1",
                        },
                    ],
                }
            ],
            "lacunas": [],
        }
    )
    client = FakeClient(LLMAnswer("gemini:test", payload, 5))
    monkeypatch.setattr(
        "preparador_audiencia.hearing_dossier.llm_client_from_spec",
        lambda spec: client,
    )

    result = generate_dossier_section(
        "proc_1",
        "depoimentos",
        primary_model="gemini:test",
        fallback_model="groq:test",
    )

    testimony = result.payload["itens"][0]
    assert testimony["papel"] == "vitima"
    assert testimony["cobertura"] == "parcial"
    assert len(testimony["trechos"]) == 1
    assert testimony["trechos"][0]["fonte"]["pagina"] == 21
    assert any("descartados" in warning for warning in result.payload["avisos"])
    assert any("curto" in warning for warning in result.payload["avisos"])


def test_dossier_retrieval_preserves_anchor_and_query_diversity(monkeypatch) -> None:
    anchored = _source("Recebo a denuncia.", page=58, chunk=1)
    pages_by_query: dict[str, int] = {}

    def fake_search(**kwargs):
        query = kwargs["queries"][0][0]
        page = pages_by_query.setdefault(query, len(pages_by_query) + 1)
        return [
            _source(f"Resultado especifico {page}", page=page),
            _source("Resultado repetido", page=90),
        ]

    monkeypatch.setattr(
        "preparador_audiencia.hearing_dossier.search_process_pattern_anchors",
        lambda *args, **kwargs: [anchored],
    )
    monkeypatch.setattr(
        "preparador_audiencia.hearing_dossier.search_process_queries_configured",
        fake_search,
    )

    results = _retrieve_diverse_sources(
        "proc_1",
        "marcos_essenciais",
        top_k=5,
        lexical_only=False,
    )

    assert [(item.page_number, item.chunk_index) for item in results] == [
        (58, 1),
        (1, 0),
        (2, 0),
        (3, 0),
        (4, 0),
    ]


def test_contradiction_requires_two_literal_excerpts(monkeypatch) -> None:
    sources = [
        _source("A testemunha afirmou que o carro era vermelho.", page=8),
        _source("Em juizo, afirmou que o carro era preto.", page=32),
    ]
    monkeypatch.setattr(
        "preparador_audiencia.hearing_dossier.search_process_queries_configured",
        lambda **kwargs: sources,
    )
    payload = json.dumps(
        {
            "itens": [
                {
                    "titulo": "Cor do veiculo",
                    "pessoa_a": "Testemunha no inquerito",
                    "afirmacao_a": {
                        "trecho_exato": "o carro era vermelho",
                        "fonte_id": "P1",
                    },
                    "pessoa_b": "Testemunha em juizo",
                    "afirmacao_b": {
                        "trecho_exato": "o carro era preto",
                        "fonte_id": "P2",
                    },
                    "explicacao": "As cores informadas sao diferentes.",
                    "relevancia_audiencia": "Confirmar condicoes de observacao.",
                },
                {
                    "titulo": "Local inventado",
                    "pessoa_a": "A",
                    "afirmacao_a": {
                        "trecho_exato": "local inexistente",
                        "fonte_id": "P1",
                    },
                    "pessoa_b": "B",
                    "afirmacao_b": {
                        "trecho_exato": "o carro era preto",
                        "fonte_id": "P2",
                    },
                    "explicacao": "Nao sustentada.",
                    "relevancia_audiencia": "Nenhuma.",
                },
            ],
            "lacunas": [],
        }
    )
    client = FakeClient(LLMAnswer("gemini:test", payload, 5))
    monkeypatch.setattr(
        "preparador_audiencia.hearing_dossier.llm_client_from_spec",
        lambda spec: client,
    )

    result = generate_dossier_section(
        "proc_1",
        "contradicoes",
        primary_model="gemini:test",
        fallback_model="groq:test",
    )

    assert len(result.payload["itens"]) == 1
    contradiction = result.payload["itens"][0]
    assert contradiction["estado"] == "potencial"
    assert contradiction["afirmacao_a"]["fonte"]["pagina"] == 8
    assert contradiction["afirmacao_b"]["fonte"]["pagina"] == 32


def test_section_uses_fallback_when_primary_returns_invalid_json(monkeypatch) -> None:
    source = _source("O fato ocorreu em 12/03/2018.", page=14)
    monkeypatch.setattr(
        "preparador_audiencia.hearing_dossier.search_process_queries_configured",
        lambda **kwargs: [source],
    )
    valid_payload = json.dumps(
        {
            "itens": [
                {
                    "tipo": "data_fato",
                    "rotulo": "Data do fato",
                    "valor": "12/03/2018",
                    "fonte_ids": ["P1"],
                }
            ],
            "lacunas": [],
        }
    )
    primary = FakeClient(LLMAnswer("gemini:test", "sem json", 3))
    fallback = FakeClient(LLMAnswer("groq:test", valid_payload, 4))
    monkeypatch.setattr(
        "preparador_audiencia.hearing_dossier.llm_client_from_spec",
        lambda spec: primary if spec.startswith("gemini") else fallback,
    )

    result = generate_dossier_section(
        "proc_1",
        "marcos_essenciais",
        primary_model="gemini:test",
        fallback_model="groq:test",
    )

    assert result.model == "groq:test"
    assert result.fallback_used is True
    assert result.payload["itens"][0]["valor"] == "12/03/2018"


def test_low_confidence_sources_do_not_reach_the_llm(monkeypatch) -> None:
    source = _source("OCR ilegivel 12/03/2018", page=14, confidence="baixa")
    monkeypatch.setattr(
        "preparador_audiencia.hearing_dossier.search_process_queries_configured",
        lambda **kwargs: [source],
    )
    monkeypatch.setattr(
        "preparador_audiencia.hearing_dossier.llm_client_from_spec",
        lambda spec: (_ for _ in ()).throw(AssertionError("LLM nao deveria ser chamada")),
    )

    result = generate_dossier_section("proc_1", "marcos_essenciais")

    assert result.model == "sistema"
    assert result.payload["itens"] == []
    assert any("confianca insuficiente" in warning for warning in result.payload["avisos"])


def test_generation_resumes_only_sections_that_did_not_finish(tmp_path, monkeypatch) -> None:
    connection = connect_database(tmp_path / "test.sqlite3")
    initialize_database(connection)
    ProcessoRepository(connection).create_pending(
        "proc_1",
        "processo.pdf",
        "storage/processo.pdf",
        "abc",
    )
    repository = HearingDossierRepository(connection)
    calls: list[str] = []
    fail_testimonies = True

    def fake_generate(processo_id, section_key, **kwargs):
        nonlocal fail_testimonies
        calls.append(section_key)
        if section_key == "depoimentos" and fail_testimonies:
            raise RuntimeError("falha temporaria")
        return SectionGenerationResult(
            payload={"itens": [], "avisos": []},
            model="gemini:test",
            fallback_used=False,
        )

    monkeypatch.setattr(
        "preparador_audiencia.hearing_dossier.generate_dossier_section",
        fake_generate,
    )

    first = generate_hearing_dossier("proc_1", repository)
    fail_testimonies = False
    calls.clear()
    second = generate_hearing_dossier("proc_1", repository)
    resumed_calls = list(calls)
    calls.clear()
    third = generate_hearing_dossier("proc_1", repository)

    assert first.status == "parcial"
    assert second.status == "concluido"
    assert resumed_calls == ["depoimentos"]
    assert third.status == "concluido"
    assert calls == []
