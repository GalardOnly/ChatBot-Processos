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

