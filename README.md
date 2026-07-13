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

Fase 3 concluida localmente: ingestao de PDF com OCR, persistencia de trechos,
indexacao vetorial no ChromaDB e busca por pergunta com paginas citadas.

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

## Fase Atual

Proxima fase recomendada: Fase 4, chat com Groq usando somente as fontes
recuperadas pela busca vetorial.
