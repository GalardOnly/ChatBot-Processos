# Preparador de Audiencia

Ferramenta para ajudar defensores publicos a analisar processos e se preparar
para audiencias.

O foco do produto e transformar autos processuais em uma experiencia pratica de
trabalho:

- entender rapidamente o caso;
- conversar com o processo por chat;
- montar linha do tempo explicada;
- identificar pontos que precisam ser confirmados em audiencia;
- sugerir perguntas;
- listar provas, documentos e pendencias;
- sempre mostrar fontes rastreaveis para revisao humana.

## Principio central

A ferramenta nao decide pelo defensor. Ela organiza, explica, pergunta e aponta
fontes para acelerar a preparacao, mantendo revisao humana obrigatoria.

## Estado atual

Fase 6 iniciada localmente: alem da ingestao, busca e chat com fontes, a
interface tem perguntas sugeridas e um roteiro guiado de preparacao de audiencia.

## Estrutura

- `backend/`: API FastAPI, extracao, OCR, ingestao, embeddings e busca vetorial.
- `docs/00-visao-produto.md`: visao e posicionamento.
- `docs/01-escopo-mvp.md`: escopo do primeiro MVP.
- `docs/02-arquitetura.md`: arquitetura v0.1.
- `docs/03-roadmap.md`: fases de execucao.
- `docs/04-decisoes-tecnicas.md`: decisoes iniciais e organizacao modular.
- `docs/05-backlog.md`: backlog priorizado.
- `docs/06-api-v01.md`: endpoints do v0.1.
- `docs/07-schema-minimo.md`: schema minimo.
- `docs/08-teste-extracao-pdf.md`: primeiro teste obrigatorio com PDF real dificil.
- `docs/09-fase-1-extracao.md`: entrega da Fase 1 e comando para testar PDF real.
- `docs/10-fase-2-ingestao.md`: API de upload, status e processamento assincrono.
- `docs/11-fase-3-embeddings-chromadb.md`: busca vetorial com BERTikal configuravel.
- `docs/12-poc-avaliacao-modelos.md`: avaliacao dos embeddings e LLMs da PoC.
- `docs/13-fase-4-chat.md`: chat com fontes, Gemini principal e fallback Groq.
- `docs/14-fase-5-interface-streamlit.md`: interface simples em Streamlit.
- `docs/15-fase-6-preparacao-audiencia.md`: perguntas sugeridas e roteiro guiado.

## Interface local

Terminal 1:

```powershell
cd backend
python -m uvicorn preparador_audiencia.main:app --host 127.0.0.1 --port 8910
```

Terminal 2:

```powershell
cd backend
python -m streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8501
```

Acesse `http://127.0.0.1:8501`.

## Avaliacao de Modelos na PoC

A PoC agora tem uma bancada para comparar modelos antes de escolher o padrao do
produto:

- recuperador `legal-ensemble`: combina BERTikal, JurisBERT e Legal-BERTimbau;
- modelos LLM: mede resposta, citacao de paginas, termos esperados e latencia;
- saida em JSON e Markdown para comparar qual modelo foi melhor.

Exemplo:

```powershell
cd backend
avaliar-poc-modelos `
  --processo-id proc_xxxxx `
  --cases eval_cases.example.json `
  --embedding legal-ensemble `
  --llm-model groq:modelo `
  --llm-model gemini:modelo `
  --output reports/poc-modelos.json
```

Para avaliar LLMs, defina `GEMINI_API_KEY` para o modelo principal ou
`GROQ_API_KEY` para o fallback. Sem chave, o comando avalia apenas a
recuperacao.

Embeddings usados em conjunto no `legal-ensemble`:

- `bertikal`: `felipemaiapolo/legalnlp-bert`;
- `jurisbert`: `alfaneo/jurisbert-base-portuguese-uncased`;
- `legal-bertimbau`: `rufimelo/Legal-BERTimbau-sts-base`.

## Decisao atual de LLM

O modelo principal da PoC e `gemini:gemini-3-flash-preview`, escolhido pela
resposta mais organizada para leitura. O unico fallback mantido e
`groq:llama-3.1-8b-instant`.
