# Fase 4: Chat com fontes do processo

## Objetivo

Permitir que o defensor converse com o processo usando apenas os trechos
recuperados pela busca vetorial.

## Entrega

Endpoint implementado:

- `POST /processo/{id}/chat`

Fluxo:

1. valida se o processo existe e esta `concluido`;
2. registra a pergunta em `chat_messages`;
3. busca os trechos relevantes no ChromaDB;
4. se nao houver fonte, responde sem chamar LLM;
5. tenta responder com `gemini:gemini-3-flash-preview`;
6. se o Gemini falhar, tenta `groq:llama-3.1-8b-instant`;
7. registra resposta, modelo usado, latencia e fontes recuperadas.

## Contrato

Entrada:

```json
{
  "pergunta": "Quais fatos preciso confirmar na audiencia?",
  "top_k": 5
}
```

Saida:

```json
{
  "processo_id": "proc_xxxxx",
  "pergunta": "Quais fatos preciso confirmar na audiencia?",
  "resposta": "A resposta vem com citacoes como [p. 3].",
  "modelo": "gemini:gemini-3-flash-preview",
  "fallback_usado": false,
  "fontes": [
    {
      "pagina": 3,
      "chunk_index": 0,
      "tipo_documento": "audiencia",
      "score": 0.87,
      "trecho": "Trecho recuperado..."
    }
  ]
}
```

## Regras

- A resposta deve ser baseada somente nas fontes recuperadas.
- O prompt pede citacao de paginas no formato `[p. N]`.
- Se nao houver fonte, o sistema responde que nao encontrou base suficiente.
- O Groq fica somente como fallback.

## Configuracao

Modelos padrao:

- principal: `gemini:gemini-3-flash-preview`;
- fallback: `groq:llama-3.1-8b-instant`.

Variaveis opcionais:

```powershell
$env:PREPARADOR_PRIMARY_LLM="gemini:gemini-3-flash-preview"
$env:PREPARADOR_FALLBACK_LLM="groq:llama-3.1-8b-instant"
```

Chaves:

```powershell
$env:GEMINI_API_KEY="sua-chave"
$env:GROQ_API_KEY="sua-chave"
```

## Validacao

Testes adicionados:

- resposta pelo modelo principal;
- fallback para Groq quando o principal falha;
- ausencia de fontes sem chamada ao LLM;
- endpoint com resposta e fontes;
- processo inexistente retornando `404`.
