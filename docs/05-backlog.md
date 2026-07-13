# Backlog Inicial

## Prioridade 1: Prova de Extração

- Criar estrutura `backend/`.
- Instalar PyMuPDF.
- Criar script de extração por página.
- Rodar extração em PDF real difícil.
- Gerar relatório de qualidade da extração.
- Decidir se OCR entra no v0.1.

## Prioridade 2: Ingestão

- Criar `POST /upload`.
- Salvar registro em `processos`.
- Calcular hash do arquivo.
- Criar status `pendente`, `processando`, `concluido`, `erro`.
- Processar PDF de forma assíncrona.
- Salvar blocos em `chunks`.

## Prioridade 3: Busca Semântica

- Escolher modelo de embedding inicial.
- Gerar vetores por bloco.
- Salvar vetores no ChromaDB.
- Persistir `vector_id` em `chunks`.
- Testar recuperação por pergunta.

## Prioridade 4: Chat

- Criar `POST /processo/{id}/chat`.
- Converter pergunta em embedding.
- Recuperar trechos relevantes no ChromaDB.
- Enviar pergunta e trechos para Groq.
- Restringir resposta às fontes.
- Retornar páginas citadas.
- Salvar pergunta, resposta e páginas recuperadas em `chat_messages`.

## Prioridade 5: Interface

- Criar tela de upload.
- Mostrar status do processamento.
- Criar chat do processo.
- Mostrar páginas citadas.
- Mostrar histórico da conversa.

## Perguntas em Aberto

- Qual PDF real difícil será usado no primeiro teste?
- O v0.1 precisa de OCR ou aceita apenas PDF com texto extraível?
- Qual modelo de embedding será usado inicialmente?
- A chave Groq ficará em `.env` local no v0.1?
- O arquivo PDF será salvo em disco no v0.1 ou apenas seu hash e texto extraído?

