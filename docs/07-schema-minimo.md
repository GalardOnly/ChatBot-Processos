# Schema Mínimo do v0.1

## `processos`

Guarda o PDF e o estado de processamento.

Campos:

- `id`;
- `filename`;
- `file_path`;
- `sha256`;
- `status`;
- `page_count`;
- `error_message`;
- `created_at`;
- `updated_at`.

## `chunks`

Guarda os blocos extraídos do processo.

Campos:

- `id`;
- `processo_id`;
- `page_number`;
- `chunk_index`;
- `text`;
- `document_type`;
- `vector_id`;
- `created_at`.

## `chat_messages`

Guarda histórico do chat.

Campos:

- `id`;
- `processo_id`;
- `role`;
- `content`;
- `retrieved_pages_json`;
- `retrieved_chunks_json`;
- `created_at`.

## Observação

No v0.1, o ChromaDB guarda os vetores e metadados de busca. O SQLite guarda o vínculo persistente com processo, página e histórico.

