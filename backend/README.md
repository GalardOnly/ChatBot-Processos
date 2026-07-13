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
python -m pip install -e .[bertikal]
$env:PREPARADOR_EMBEDDING_PROVIDER="bertikal"
$env:PREPARADOR_EMBEDDING_MODEL="felipemaiapolo/legalnlp-bert"
```

O ChromaDB fica em `chroma/` por padrao. Para mudar:

```powershell
$env:PREPARADOR_CHROMA_DIR="C:\caminho\chroma"
```
