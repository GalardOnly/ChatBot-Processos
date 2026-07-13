# Decisões Técnicas Iniciais

## Estrutura do Repositório

Começar em monorepo local:

- `backend/`;
- `frontend/`;
- `docs/`;
- `samples/`;
- `scripts/`.

## Backend

- Python;
- FastAPI;
- PyMuPDF para extração de PDF;
- RapidOCR/ONNXRuntime como OCR local para páginas escaneadas;
- SQLite no v0.1;
- ChromaDB para vetores;
- processamento assíncrono simples;
- pytest;
- Ruff.

## Frontend

- Streamlit no v0.1, pela velocidade de validação;
- migração para React fica para depois da validação do fluxo.

## IA

- embeddings para busca semântica no processo;
- ChromaDB com coleção por processo;
- Groq para resposta via LLM;
- prompt restrito aos trechos recuperados;
- resposta sempre com páginas citadas;
- fallback obrigatório quando não houver fonte suficiente.

## Endpoints Fixos do v0.1

- `POST /upload`;
- `GET /processo/{id}/status`;
- `POST /processo/{id}/chat`.

## Decisão Crítica

O primeiro teste técnico será extração com PDF real difícil. Não vale avançar para chat, embeddings ou interface sem saber se o texto extraído por página é minimamente confiável.

## Termos de UI

Usar:

- processo;
- página;
- trecho;
- fonte;
- resposta;
- pergunta.

Evitar na UI:

- chunk;
- embedding;
- vetor;
- ChromaDB;
- payload;
- prompt.
