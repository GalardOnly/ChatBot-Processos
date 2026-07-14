from __future__ import annotations

import time
from typing import Any

import httpx
import streamlit as st

DEFAULT_API_URL = "http://127.0.0.1:8910"


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
    _render_chat(st.session_state.api_url)


def _init_state() -> None:
    defaults = {
        "api_url": DEFAULT_API_URL,
        "processo_id": "",
        "status": None,
        "messages": [],
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

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("fontes"):
                _render_sources(message["fontes"])

    pergunta = st.chat_input("Pergunte sobre o processo")
    if pergunta:
        st.session_state.messages.append({"role": "user", "content": pergunta})
        with st.chat_message("user"):
            st.markdown(pergunta)
        with st.chat_message("assistant"):
            with st.spinner("Consultando o processo..."):
                answer = _ask_question(api_url, pergunta)
            st.markdown(answer["content"])
            _render_sources(answer.get("fontes", []))
        st.session_state.messages.append(answer)


def _ask_question(api_url: str, pergunta: str) -> dict[str, Any]:
    processo_id = st.session_state.processo_id
    try:
        response = httpx.post(
            f"{api_url}/processo/{processo_id}/chat",
            json={"pergunta": pergunta, "top_k": 5},
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
