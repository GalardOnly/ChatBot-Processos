# Backend

Backend do Preparador de Audiencia.

## Instalacao local

```powershell
python -m pip install -e .[dev,models]
```

## Rodar extracao em um PDF

```powershell
extrair-pdf-processo "C:\caminho\processo.pdf" --output "relatorio-extracao.json"
```

O relatorio preserva numero da pagina, quantidade de caracteres extraidos,
amostra do texto e alertas de qualidade.

Por padrao, o comando aplica OCR em paginas com imagem e pouco texto nativo
extraido. Para comparar apenas a extracao do PyMuPDF:

```powershell
extrair-pdf-processo "C:\caminho\processo.pdf" --no-ocr --output "relatorio-sem-ocr.json"
```

## Rodar API local

```powershell
python -m uvicorn preparador_audiencia.main:app --host 127.0.0.1 --port 8910
```

Rotas implementadas:

- `POST /upload`
- `GET /processo/{id}/status`
- `POST /processo/{id}/buscar`
- `POST /processo/{id}/chat`

## Rodar interface Streamlit

Com a API rodando em outro terminal:

```powershell
python -m streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8501
```

Acesse `http://127.0.0.1:8501`.

## Chat do processo

O chat usa os trechos recuperados pela busca vetorial e instrui o LLM a
responder somente com base nessas fontes, citando paginas no formato `[p. N]`.

Modelo padrao:

- principal: `gemini:gemini-3-flash-preview`;
- fallback: `groq:llama-3.1-8b-instant`.

Exemplo:

```powershell
curl -X POST http://127.0.0.1:8910/processo/proc_xxxxx/chat `
  -H "Content-Type: application/json" `
  -d "{\"pergunta\":\"Quais fatos preciso confirmar na audiencia?\",\"top_k\":5}"
```

Variaveis opcionais para trocar os modelos sem mudar codigo:

```powershell
$env:PREPARADOR_PRIMARY_LLM="gemini:gemini-3-flash-preview"
$env:PREPARADOR_FALLBACK_LLM="groq:llama-3.1-8b-instant"
```

## Embeddings e busca vetorial

Por padrao, o fluxo principal usa o recuperador `legal-ensemble`, que indexa e
consulta os trechos com JurisBERT e Legal-BERTimbau, combinando os resultados
antes de enviar fontes ao Gemini. O BERTikal continua disponivel para testes
isolados.

Para usar o modo leve de desenvolvimento e testes locais:

```powershell
$env:PREPARADOR_EMBEDDING_PROVIDER="hash"
```

Para forcar o ensemble juridico:

```powershell
$env:PREPARADOR_EMBEDDING_PROVIDER="legal-ensemble"
```

Para testar um modelo isolado, por exemplo BERTikal:

```powershell
python -m pip install -e .[models]
$env:PREPARADOR_EMBEDDING_PROVIDER="bertikal"
$env:PREPARADOR_EMBEDDING_MODEL="felipemaiapolo/legalnlp-bert"
```

O ChromaDB fica em `chroma/` por padrao. Para mudar:

```powershell
$env:PREPARADOR_CHROMA_DIR="C:\caminho\chroma"
```

## Avaliar modelos na PoC

Crie um arquivo de casos com perguntas, paginas esperadas e termos esperados.
Use `eval_cases.example.json` como ponto de partida.

```powershell
avaliar-poc-modelos `
  --processo-id proc_xxxxx `
  --cases eval_cases.example.json `
  --embedding legal-ensemble `
  --llm-model gemini:gemini-3-flash-preview `
  --llm-model groq:llama-3.1-8b-instant `
  --top-k 5 `
  --output reports/poc-modelos.json
```

Por seguranca, o avaliador limita chamadas de LLM a 4 por execucao. Antes de
rodar valendo, confira o plano:

```powershell
avaliar-poc-modelos `
  --processo-id proc_xxxxx `
  --cases eval_cases.example.json `
  --embedding legal-ensemble `
  --llm-model gemini:gemini-3-flash-preview `
  --llm-model groq:llama-3.1-8b-instant `
  --dry-run
```

Para uma bateria maior, aumente explicitamente:

```powershell
avaliar-poc-modelos ... --max-llm-calls 8
```

O comando gera:

- `reports/poc-modelos.json`: dados completos da avaliacao;
- `reports/poc-modelos.md`: tabela legivel com melhor embedding e melhor LLM.

Para usar LLMs na PoC:

```powershell
$env:GEMINI_API_KEY="sua-chave"
$env:GROQ_API_KEY="sua-chave"
```

Se preferir, coloque as chaves em `backend/.env`; ele e carregado
automaticamente e esta ignorado pelo Git.

Decisao atual da PoC:

- principal: `gemini:gemini-3-flash-preview`;
- fallback: `groq:llama-3.1-8b-instant`.

Os IDs de modelos mudam com o tempo. Consulte a lista ativa dos provedores antes
de rodar uma bateria grande.

Aliases de embedding disponiveis:

- `bertikal`: usa `felipemaiapolo/legalnlp-bert` com mean pooling;
- `jurisbert`: usa `alfaneo/jurisbert-base-portuguese-uncased` com mean pooling;
- `legal-bertimbau`: usa `rufimelo/Legal-BERTimbau-sts-base` via sentence-transformers.
- `legal-ensemble`: usa JurisBERT e Legal-BERTimbau em paralelo e combina os rankings.

## Benchmark por familias

JurisTCU, para recuperacao juridica:

```powershell
python -m preparador_audiencia.benchmark_cli juristcu --queries 20 --distractors 1000 --embedding legal-ensemble --top-k 10
```

PDFs publicos, para extracao e OCR:

```powershell
python -m preparador_audiencia.benchmark_cli pdfs ..\samples\benchmark\*.pdf --family pdfs-publicos --max-pages 5
```

PDFs reais anonimizados devem ficar em `samples/anonimizados/` e usar
`benchmark_cases.anonimizado.example.json` como ponto de partida para perguntas
e paginas esperadas.
