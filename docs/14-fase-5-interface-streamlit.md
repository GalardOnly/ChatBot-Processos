# Fase 5: Interface Streamlit

## Objetivo

Entregar uma interface simples para validar o fluxo inteiro com o defensor sem
criar ainda um frontend completo.

## Escopo

A interface tem uma tela unica com:

- upload do PDF;
- status do processamento;
- identificador do processo;
- chat do processo;
- fontes recuperadas em painel expansivel.

## Como rodar

Terminal 1, API:

```powershell
cd backend
python -m uvicorn preparador_audiencia.main:app --host 127.0.0.1 --port 8910
```

Terminal 2, interface:

```powershell
cd backend
python -m streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8501
```

Depois acesse:

```text
http://127.0.0.1:8501
```

## Observacoes

- O Streamlit fala com a API local em `http://127.0.0.1:8910`.
- A URL da API pode ser alterada na barra lateral.
- O chat so aparece quando o processo esta `concluido`.
- Esta tela e propositalmente simples para validar utilidade antes de investir
  em frontend mais elaborado.
