from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).parents[1] / "streamlit_app.py"


def _completed_status() -> dict[str, object]:
    return {
        "status": "concluido",
        "consulta_disponivel": True,
        "etapa": "concluido",
        "paginas_extraidas": 10,
        "chunks": 20,
        "progresso_percentual": 100,
        "mensagem": "Processo pronto para consulta",
        "erro": None,
        "reprocessamento_necessario": False,
        "modo_busca": "hibrida",
    }


def test_criminal_analysis_tab_is_available_for_completed_process() -> None:
    app = AppTest.from_file(str(APP_PATH))
    app.session_state["processo_id"] = "proc_teste"
    app.session_state["status"] = _completed_status()

    app.run(timeout=10)

    assert not list(app.exception)
    assert [tab.label for tab in app.tabs] == [
        "Chat",
        "Analise criminal",
        "Preparacao de audiencia",
    ]
    buttons = {button.label: button for button in app.button}
    assert buttons["Gerar analise criminal"].disabled is False
    assert buttons["Limpar analise"].disabled is True
    assert any(
        "nao calcula nem declara prescricao" in warning.value
        for warning in app.warning
    )
    assert any(
        "Fotos e prints ainda nao sao interpretados visualmente" in caption.value
        for caption in app.caption
    )


def test_criminal_analysis_waits_for_completed_process() -> None:
    app = AppTest.from_file(str(APP_PATH)).run(timeout=10)

    assert not list(app.exception)
    assert all(button.label != "Gerar analise criminal" for button in app.button)


def test_criminal_analysis_renders_operational_nullity_conclusion() -> None:
    app = AppTest.from_file(str(APP_PATH))
    app.session_state["processo_id"] = "proc_teste"
    app.session_state["status"] = _completed_status()
    app.session_state["criminal_analysis_report"] = [
        {
            "key": "nulidade_reconhecimento",
            "title": "Nulidade: reconhecimento de pessoas",
            "analysis": {
                "conclusao": "forte_fundamento_para_alegar_invalidade",
                "conclusao_rotulo": (
                    "Forte fundamento para alegar invalidade do reconhecimento"
                ),
                "confianca": "alta",
                "resumo": "A fotografia foi apresentada isoladamente.",
                "justificativa_aplicabilidade": "A vitima nao conhecia o suspeito.",
                "impacto_processual": (
                    "reconhecimento_determinante_sem_prova_independente"
                ),
                "justificativa_impacto": "Nao foi localizada prova independente.",
                "paginas_impacto": [7],
                "requisitos": [
                    {
                        "titulo": "Procedimento nao sugestivo",
                        "resultado": "nao_observado",
                        "justificativa": "Foi exibida apenas uma fotografia.",
                        "paginas": [7],
                        "fontes_juridicas": ["stj_tema_1258"],
                    }
                ],
                "providencias": ["Avaliar a arguicao defensiva."],
                "lacunas": ["Conferir o auto de reconhecimento."],
                "avisos": [],
                "fontes_processuais": [],
                "fontes_juridicas": [
                    {
                        "titulo": "Tema Repetitivo 1.258 do STJ",
                        "autoridade": "Superior Tribunal de Justica",
                        "referencia": "Terceira Secao",
                        "url": "https://processo.stj.jus.br/",
                    }
                ],
                "versao_catalogo_juridico": "2026.08.02",
                "catalogo_verificado_em": "2026-08-02",
                "modelo": "gemini:test",
                "fallback_usado": False,
            },
        }
    ]

    app.run(timeout=10)

    assert not list(app.exception)
    assert any(
        "Forte fundamento para alegar invalidade" in error.value
        for error in app.error
    )
    assert any(
        expander.label == "Fundamentos juridicos oficiais"
        for expander in app.expander
    )
