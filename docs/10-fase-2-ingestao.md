# Fase 2: Ingestão Assíncrona

## Objetivo

Transformar a extração da Fase 1 em uma API capaz de receber PDFs completos, salvar o arquivo, processar em background e expor o status do processamento.

## Entregas Criadas

- `POST /upload`;
- `GET /processo/{id}/status`;
- banco SQLite com tabelas `processos`, `chunks` e `chat_messages`;
- salvamento local do PDF;
- cálculo de SHA-256;
- status `pendente`, `processando`, `concluido` e `erro`;
- chunking por página com índice do bloco;
- persistência dos chunks extraídos;
- smoke HTTP com PDF público.

## Como Rodar

```powershell
cd "C:\Users\User\Desktop\Projetos\Classificador de Processos\backend"
python -m uvicorn preparador_audiencia.main:app --host 127.0.0.1 --port 8910
```

## Smoke HTTP Realizado

Arquivo usado:

- `samples/publicos/stj-hc-233262-sp.pdf`

Resultado:

- `POST /upload`: `200`;
- status inicial: `pendente`;
- status intermediário: `processando`;
- status final: `concluido`;
- páginas extraídas: `10`;
- chunks persistidos: `18`;
- erro: `null`.

## Verificações

- `pytest`: 15 testes passaram;
- `ruff check .`: sem erros.

## Próximo Passo

Fase 3: embeddings e ChromaDB. O objetivo será gerar vetores para cada chunk e recuperar trechos relevantes por pergunta.
