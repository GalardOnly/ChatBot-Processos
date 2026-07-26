# Banco de perguntas para audiencia

Esta fase cria uma base inicial de perguntas que ajudam a testar a PoC mesmo sem feedback constante de um defensor.

O banco nao tenta substituir a estrategia juridica. Ele serve para guiar o uso do chat: resumo, linha do tempo, documentos, contradicoes, riscos, perguntas para pessoa assistida e perguntas por tipo de audiencia.

As perguntas estao organizadas por area, tipo de audiencia, objetivo, quando usar, tags e prioridade. Isso permite que a interface futuramente mostre sugestoes adequadas ao contexto do processo.

## Areas iniciais

- Geral
- Criminal
- Audiencia de custodia
- Violencia domestica e medidas protetivas
- Familia
- Civel e consumidor
- Execucao penal

## Como listar perguntas

```powershell
perguntas-audiencia --area criminal --tag custodia --limit 3
```

## Como exportar para Markdown

```powershell
perguntas-audiencia `
  --format markdown `
  --output reports/perguntas-audiencia.md
```

## Como gerar casos para benchmark

```powershell
perguntas-audiencia `
  --area geral `
  --limit 6 `
  --format cases-json `
  --output reports/perguntas-gerais.cases.json
```

Esse arquivo pode ser usado no benchmark de respostas.

```powershell
benchmark-respostas `
  --processo-id proc_xxxxx `
  --cases reports/perguntas-gerais.cases.json `
  --embedding legal-ensemble `
  --limit-cases 2 `
  --max-llm-calls 6 `
  --output reports/benchmark-respostas-gerais.json
```

Como esses casos sao exploratorios, eles nao trazem paginas esperadas. A avaliacao principal vem do avaliador LLM, que compara a resposta com as fontes recuperadas.

## Endpoint

A API tambem expoe a lista.

```text
GET /perguntas-audiencia
GET /perguntas-audiencia?area=criminal&tag=custodia&limit=3
```

Esse endpoint sera usado depois pelo Streamlit para substituir as perguntas fixas que hoje ficam dentro da interface.
