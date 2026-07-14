# Roadmap

## Fase 0: Fundação do Produto

Objetivo: documentar o produto certo antes de codar.

Entregas:

- visão do produto;
- escopo do MVP;
- arquitetura v0.1;
- endpoints;
- schema mínimo;
- backlog.

## Fase 1: Prova de Extração em PDF Real Difícil

Objetivo: validar o principal risco antes do pipeline de IA.

Entregas:

- script local com PyMuPDF;
- relatório por página;
- contagem de texto extraído;
- identificação de páginas vazias ou ruins;
- amostra de saída preservando número da página.

Critério de pronto:

- um PDF real e ruim é processado;
- sabemos quais páginas têm texto aproveitável;
- sabemos se OCR será necessário já no v0.1 ou se pode ficar para depois.

## Fase 2: Ingestão Assíncrona do Processo

Objetivo: receber PDF completo e processar sem travar a interface.

Entregas:

- `POST /upload`;
- persistência em `processos`;
- status de processamento;
- extração por página;
- subdivisão de páginas longas em blocos;
- persistência em `chunks`.

Critério de pronto:

- PDF grande pode ser enviado;
- usuário consegue consultar status;
- cada bloco preserva página e índice.

## Fase 3: Embeddings e ChromaDB

Objetivo: tornar o processo pesquisável semanticamente.

Entregas:

- geração de embeddings;
- coleção por processo no ChromaDB;
- metadata de página e tipo de documento;
- vínculo entre `chunks.vector_id` e ChromaDB.

Critério de pronto:

- pergunta de teste recupera trechos do processo correto;
- resultados retornam páginas e textos de origem.

## Fase 4: Chat com Gemini, fallback Groq e Citações

Objetivo: permitir conversa com o processo.

Entregas:

- `POST /processo/{id}/chat`;
- busca dos trechos relevantes;
- prompt restrito às fontes recuperadas;
- chamada ao Gemini como modelo principal;
- fallback para Groq quando o Gemini falhar;
- resposta com páginas citadas;
- persistência em `chat_messages`.

Critério de pronto:

- resposta não usa conhecimento fora do processo;
- resposta cita páginas;
- se faltarem fontes, o sistema diz que não encontrou base suficiente.

## Fase 5: Interface v0.1

Objetivo: entregar uma experiência mínima utilizável pelo defensor.

Entregas:

- interface simples em Streamlit;
- upload do PDF;
- status do processamento;
- chat do processo;
- exibição das páginas citadas;
- fontes recuperadas em painel expansível.

## Fase 6: Preparação de Audiência

Objetivo: transformar o chat em ferramenta de preparação.

Entregas:

- perguntas sugeridas;
- linha do tempo explicada;
- provas e pendências;
- resumo orientado à audiência;
- fontes por item;
- roteiro guiado em Streamlit para gerar a preparacao completa.

## Fase 7: Segurança, LGPD e Validação

Objetivo: preparar uso responsável.

Entregas:

- política de dados;
- logs seguros;
- auditoria;
- revisão de provedores externos;
- validação com defensores.
