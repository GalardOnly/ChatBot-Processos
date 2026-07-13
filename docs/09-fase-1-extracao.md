# Fase 1: Prova de Extração

## Objetivo

Validar a extração de texto por página com PyMuPDF antes de implementar ChromaDB, Groq ou interface.

## Entregas Criadas

- pacote `backend/`;
- função `extract_pdf_report`;
- CLI `extrair-pdf-processo`;
- testes automatizados com PDF sintético;
- relatório com página, caracteres, palavras, amostra e alertas de qualidade.

## Como Rodar em um PDF Real

```powershell
cd "C:\Users\User\Desktop\Projetos\Classificador de Processos\backend"
python -m pip install -e .[dev]
extrair-pdf-processo "C:\caminho\para\processo-real-ruim.pdf" --output "..\reports\extracao-processo-real.json"
```

## O Que Avaliar

- Quantas páginas vieram sem texto?
- Quantas páginas vieram com pouco texto?
- As páginas citadas no relatório batem com o PDF?
- A amostra de texto é legível?
- OCR precisa entrar já no v0.1?

## Status

Infraestrutura pronta e validada com PDF sintético.

Verificações locais:

- `pytest`: 3 testes passaram;
- `ruff check .`: sem erros;
- CLI `extrair-pdf-processo`: gerou relatório JSON preservando páginas e detectando página sem texto.

Falta rodar em um PDF real difícil fornecido ou aprovado pelo defensor.
