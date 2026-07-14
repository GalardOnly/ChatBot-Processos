from __future__ import annotations

import time
from typing import Any

import httpx
import streamlit as st

DEFAULT_API_URL = "http://127.0.0.1:8910"
GUIDED_QUESTIONS = [
    (
        "Preparar audiencia",
        "Prepare um roteiro pratico para a audiencia deste processo. "
        "Inclua resumo do caso, pontos de atencao, fatos a confirmar, provas importantes "
        "e perguntas sugeridas. Cite as paginas em cada item.",
    ),
    (
        "Perguntas para a parte assistida",
        "Quais perguntas o defensor deve fazer para a parte assistida antes ou durante "
        "a audiencia? Separe por tema, explique o objetivo de cada pergunta e cite as paginas.",
    ),
    (
        "Pontos para contraditar",
        "Quais pontos do processo podem ser contraditados, esclarecidos ou questionados "
        "em audiencia? Indique o fundamento de cada ponto e cite as paginas.",
    ),
    (
        "Documentos que preciso abrir",
        "Quais documentos, laudos, decisoes, mandados, certidoes ou provas o defensor "
        "deve abrir e conferir antes da audiencia? "
        "Explique por que cada um importa e cite paginas.",
    ),
    (
        "Riscos e urgencias",
        "Identifique riscos, urgencias, prazos, determinacoes judiciais, contradicoes ou "
        "pontos sensiveis que podem impactar a audiencia. Cite as paginas usadas.",
    ),
    (
        "Resumo de 2 minutos",
        "Faça um resumo de ate 2 minutos para o defensor lembrar rapidamente do caso "
        "antes da audiencia. Foque no que e essencial e cite as paginas principais.",
    ),
]
HEARING_SECTIONS = [
    {
        "title": "Resumo do caso",
        "prompt": (
            "Prepare um resumo do caso para audiencia. Traga fatos centrais, partes, "
            "pedido ou acusacao principal e pontos que exigem atencao. "
            "Use topicos e cite paginas em cada item."
        ),
    },
    {
        "title": "Linha do tempo",
        "prompt": (
            "Monte uma linha do tempo explicada dos eventos processuais e factuais relevantes. "
            "Para cada evento, informe data quando houver, fato associado e pagina."
        ),
    },
    {
        "title": "Provas e documentos",
        "prompt": (
            "Liste provas, documentos, laudos, mandados, decisoes e certidoes importantes. "
            "Explique a relevancia pratica de cada um para a audiencia e cite paginas."
        ),
    },
    {
        "title": "Pontos controvertidos",
        "prompt": (
            "Identifique contradicoes, lacunas, pontos confusos ou fatos que precisam "
            "ser validados pelo defensor antes ou durante a audiencia. Cite paginas."
        ),
    },
    {
        "title": "Perguntas sugeridas",
        "prompt": (
            "Sugira perguntas para a audiencia, separadas por pessoa ou tema quando possivel. "
            "Explique o objetivo de cada grupo de perguntas e cite paginas de apoio."
        ),
    },
    {
        "title": "Checklist final",
        "prompt": (
            "Crie um checklist final de preparacao para audiencia. Inclua providencias, "
            "documentos a conferir, pontos a explicar para a pessoa assistida e riscos. "
            "Cite paginas sempre que houver base no processo."
        ),
    },
]


def main() -> None:
    st.set_page_config(page_title="Preparador de Audiencia", layout="wide")
    _init_state()

    st.title("Preparador de Audiencia")
    st.caption("Upload do processo, status de processamento e chat com fontes citadas.")

    api_url = st.sidebar.text_input("API local", value=st.session_state.api_url)
    st.session_state.api_url = api_url.rstrip("/")
    st.sidebar.caption("Padrao: FastAPI em http://127.0.0.1:8910")
    _render_process_recovery(st.session_state.api_url)

    uploaded_file = st.file_uploader("PDF do processo", type=["pdf"])
    col_upload, col_status = st.columns([1, 1])

    with col_upload:
        if st.button("Enviar PDF", type="primary", disabled=uploaded_file is None):
            if uploaded_file is not None:
                _upload_pdf(st.session_state.api_url, uploaded_file)

    with col_status:
        if st.button("Atualizar status", disabled=not st.session_state.processo_id):
            _refresh_status(st.session_state.api_url)

    _render_process_status()
    st.divider()
    chat_tab, preparation_tab = st.tabs(["Chat", "Preparacao de audiencia"])
    with chat_tab:
        _render_chat(st.session_state.api_url)
    with preparation_tab:
        _render_hearing_preparation(st.session_state.api_url)


def _init_state() -> None:
    defaults = {
        "api_url": DEFAULT_API_URL,
        "processo_id": "",
        "status": None,
        "messages": [],
        "hearing_report": [],
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _upload_pdf(api_url: str, uploaded_file: Any) -> None:
    try:
        response = httpx.post(
            f"{api_url}/upload",
            files={
                "file": (
                    uploaded_file.name,
                    uploaded_file.getvalue(),
                    "application/pdf",
                )
            },
            timeout=120,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        st.error(f"Nao foi possivel enviar o PDF: {exc}")
        return

    payload = response.json()
    st.session_state.processo_id = payload["processo_id"]
    st.session_state.messages = []
    st.session_state.hearing_report = []
    _refresh_status(api_url)
    st.success("PDF enviado. Aguarde o processamento terminar.")


def _refresh_status(api_url: str) -> None:
    processo_id = st.session_state.processo_id
    if not processo_id:
        return
    try:
        response = httpx.get(f"{api_url}/processo/{processo_id}/status", timeout=30)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        st.error(f"Nao foi possivel consultar o status: {exc}")
        return
    st.session_state.status = response.json()


def _render_process_recovery(api_url: str) -> None:
    st.sidebar.divider()
    st.sidebar.subheader("Recuperar processo")
    typed_id = st.sidebar.text_input("ID do processo", value=st.session_state.processo_id)
    col_load, col_latest = st.sidebar.columns(2)
    with col_load:
        if st.button("Carregar", disabled=not typed_id.strip()):
            st.session_state.processo_id = typed_id.strip()
            st.session_state.messages = []
            st.session_state.hearing_report = []
            _refresh_status(api_url)
            st.rerun()
    with col_latest:
        if st.button("Ultimo"):
            _load_latest_process(api_url, completed_only=False)
            st.rerun()
    if st.sidebar.button("Ultimo concluido"):
        _load_latest_process(api_url, completed_only=True)
        st.rerun()


def _load_latest_process(api_url: str, *, completed_only: bool) -> None:
    try:
        response = httpx.get(f"{api_url}/processos?limit=10", timeout=30)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        st.sidebar.error(f"Nao foi possivel carregar o ultimo processo: {exc}")
        return

    processos = response.json()["processos"]
    if completed_only:
        processos = [processo for processo in processos if processo["status"] == "concluido"]
    if not processos:
        st.sidebar.info("Nenhum processo encontrado.")
        return
    st.session_state.processo_id = processos[0]["processo_id"]
    st.session_state.messages = []
    st.session_state.hearing_report = []
    _refresh_status(api_url)


def _render_process_status() -> None:
    processo_id = st.session_state.processo_id
    status = st.session_state.status
    if not processo_id:
        st.info("Envie um PDF para iniciar a analise.")
        return

    st.subheader("Processo")
    st.code(processo_id, language=None)

    if not status:
        st.warning("Status ainda nao consultado.")
        return

    cols = st.columns(4)
    cols[0].metric("Status", status["status"])
    cols[1].metric("Paginas", status["paginas_extraidas"])
    cols[2].metric("Chunks", status["chunks"])
    cols[3].metric("Erro", status["erro"] or "-")

    if status["status"] in {"pendente", "processando"}:
        time.sleep(1)
        st.rerun()


def _render_chat(api_url: str) -> None:
    st.subheader("Chat do processo")
    status = st.session_state.status or {}
    ready = status.get("status") == "concluido"

    if not ready:
        st.caption("O chat fica disponivel quando o processamento estiver concluido.")
        return

    _render_guided_questions(api_url)

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("fontes"):
                _render_sources(message["fontes"])

    pergunta = st.chat_input("Pergunte sobre o processo")
    if pergunta:
        _submit_chat_question(api_url, pergunta)


def _render_guided_questions(api_url: str) -> None:
    with st.expander("Perguntas sugeridas", expanded=True):
        columns = st.columns(3)
        for index, (label, prompt) in enumerate(GUIDED_QUESTIONS):
            with columns[index % len(columns)]:
                if st.button(label, use_container_width=True):
                    _submit_chat_question(api_url, prompt)
                    st.rerun()


def _submit_chat_question(api_url: str, pergunta: str) -> None:
    st.session_state.messages.append({"role": "user", "content": pergunta})
    with st.chat_message("user"):
        st.markdown(pergunta)
    with st.chat_message("assistant"):
        with st.spinner("Consultando o processo..."):
            answer = _ask_question(api_url, pergunta)
        st.markdown(answer["content"])
        _render_sources(answer.get("fontes", []))
    st.session_state.messages.append(answer)


def _render_hearing_preparation(api_url: str) -> None:
    st.subheader("Preparacao de audiencia")
    status = st.session_state.status or {}
    ready = status.get("status") == "concluido"

    if not ready:
        st.caption("A preparacao fica disponivel quando o processamento estiver concluido.")
        return

    col_generate, col_clear = st.columns([1, 1])
    with col_generate:
        if st.button("Gerar roteiro de audiencia", type="primary"):
            _generate_hearing_report(api_url)
    with col_clear:
        if st.button("Limpar roteiro", disabled=not st.session_state.hearing_report):
            st.session_state.hearing_report = []
            st.rerun()

    if not st.session_state.hearing_report:
        st.info("Use o botao acima para gerar uma preparacao guiada com fontes.")
        return

    for section in st.session_state.hearing_report:
        with st.expander(section["title"], expanded=True):
            st.markdown(section["content"])
            _render_sources(section.get("fontes", []))


def _generate_hearing_report(api_url: str) -> None:
    report = []
    progress = st.progress(0)
    status_text = st.empty()
    for index, section in enumerate(HEARING_SECTIONS, start=1):
        status_text.write(f"Gerando: {section['title']}")
        answer = _ask_question(api_url, section["prompt"], top_k=8)
        report.append(
            {
                "title": section["title"],
                "content": answer["content"],
                "fontes": answer.get("fontes", []),
            }
        )
        progress.progress(index / len(HEARING_SECTIONS))
    status_text.empty()
    st.session_state.hearing_report = report


def _ask_question(api_url: str, pergunta: str, top_k: int = 5) -> dict[str, Any]:
    processo_id = st.session_state.processo_id
    try:
        response = httpx.post(
            f"{api_url}/processo/{processo_id}/chat",
            json={"pergunta": pergunta, "top_k": top_k},
            timeout=120,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return {
            "role": "assistant",
            "content": f"Nao foi possivel consultar o chat: {exc}",
            "fontes": [],
        }

    payload = response.json()
    model_note = f"\n\nModelo usado: `{payload['modelo']}`"
    if payload["fallback_usado"]:
        model_note += " (fallback)"
    return {
        "role": "assistant",
        "content": payload["resposta"] + model_note,
        "fontes": payload["fontes"],
    }


def _render_sources(fontes: list[dict[str, Any]]) -> None:
    if not fontes:
        return
    with st.expander("Fontes recuperadas"):
        for fonte in fontes:
            st.markdown(
                f"**Pagina {fonte['pagina']}**, chunk {fonte['chunk_index']} "
                f"- score {fonte['score']:.3f}"
            )
            st.write(fonte["trecho"])


if __name__ == "__main__":
    main()
