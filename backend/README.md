# Backend

Fase 1 do v0.1: extração de texto por página com PyMuPDF e relatório de qualidade.

## Instalação local

```powershell
python -m pip install -e .[dev]
```

## Rodar extração em um PDF

```powershell
extrair-pdf-processo "C:\caminho\processo.pdf" --output "relatorio-extracao.json"
```

O relatório preserva número da página, quantidade de caracteres extraídos, amostra do texto e alertas de qualidade.

Por padrão, o comando aplica OCR em páginas com imagem e pouco texto nativo extraído. Para comparar apenas a extração do PyMuPDF:

```powershell
extrair-pdf-processo "C:\caminho\processo.pdf" --no-ocr --output "relatorio-sem-ocr.json"
```

## Rodar API local

```powershell
python -m uvicorn preparador_audiencia.main:app --host 127.0.0.1 --port 8910
```

Rotas da Fase 2:

- `POST /upload`
- `GET /processo/{id}/status`
