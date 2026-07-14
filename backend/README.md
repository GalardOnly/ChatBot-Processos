# Backend

Backend do Preparador de Audiencia.

## Instalacao local

```powershell
python -m pip install -e .[dev]
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

## Embeddings e busca vetorial

Por padrao, o backend usa um provider leve (`hash`) para desenvolvimento e
testes locais:

```powershell
$env:PREPARADOR_EMBEDDING_PROVIDER="hash"
```

Para usar o BERTikal:

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
  --llm-model groq:modelo `
  --llm-model gemini:gemini-flash-latest `
  --llm-model ollama:deepseek-r1:latest `
  --llm-model openai:modelo `
  --llm-model deepseek:modelo `
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
  --llm-model groq:modelo `
  --llm-model gemini:gemini-flash-latest `
  --dry-run
```

Para uma bateria maior, aumente explicitamente:

```powershell
avaliar-poc-modelos ... --max-llm-calls 8
```

O comando gera:

- `reports/poc-modelos.json`: dados completos da avaliacao;
- `reports/poc-modelos.md`: tabela legivel com melhor embedding e melhor LLM.

Para usar LLMs:

```powershell
$env:GROQ_API_KEY="sua-chave"
$env:GEMINI_API_KEY="sua-chave"
$env:OPENAI_API_KEY="sua-chave"
$env:DEEPSEEK_API_KEY="sua-chave"
```

Se preferir, coloque as chaves em `backend/.env`; ele e carregado
automaticamente e esta ignorado pelo Git.

Para usar Ollama local, nao precisa de chave:

```powershell
ollama list
avaliar-poc-modelos `
  --processo-id proc_xxxxx `
  --cases eval_cases.example.json `
  --embedding legal-ensemble `
  --llm-model ollama:deepseek-r1:latest `
  --output reports/poc-ollama.json
```

Os IDs de modelos mudam com o tempo. Consulte a lista ativa de cada provedor
antes de rodar uma bateria grande.

Aliases de embedding disponiveis:

- `bertikal`: usa `felipemaiapolo/legalnlp-bert` com mean pooling;
- `jurisbert`: usa `alfaneo/jurisbert-base-portuguese-uncased` com mean pooling;
- `legal-bertimbau`: usa `rufimelo/Legal-BERTimbau-sts-base` via sentence-transformers.
- `legal-ensemble`: usa os tres acima em paralelo e combina os rankings.
