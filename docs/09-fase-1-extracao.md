# Fase 1: Prova de Extração

## Objetivo

Validar a extração de texto por página com PyMuPDF antes de implementar ChromaDB, Groq ou interface.

## Entregas Criadas

- pacote `backend/`;
- função `extract_pdf_report`;
- CLI `extrair-pdf-processo`;
- OCR automático com RapidOCR/ONNXRuntime para páginas com imagem e pouco texto;
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

- `pytest`: 4 testes passaram;
- `ruff check .`: sem erros;
- CLI `extrair-pdf-processo`: gerou relatório JSON preservando páginas e detectando página sem texto.
- OCR real executado com RapidOCR nos PDFs públicos digitalizados do STJ.

Teste com PDFs públicos digitalizados do STJ:

- três editais públicos marcados como "Documento digitalizado juntado ao processo" foram baixados para `samples/publicos/digitalizados/`;
- cada página continha imagem embutida;
- o PyMuPDF extraiu apenas o cabeçalho textual pesquisável;
- o relatório agora marca esse cenário como `imagem_com_texto_curto` e `provavel_necessidade_de_ocr`.
- com OCR ativo, o texto recuperado subiu de aproximadamente 117-124 caracteres nativos para 1.319-1.579 caracteres totais por documento.

Resultados com OCR:

| PDF público | Texto nativo | Texto OCR | Texto total | Método |
| --- | ---: | ---: | ---: | --- |
| `stj-documento-digitalizado-fl143.pdf` | 124 | 1453 | 1579 | `native_plus_ocr` |
| `stj-documento-digitalizado-fl483.pdf` | 117 | 1200 | 1319 | `native_plus_ocr` |
| `stj-documento-digitalizado-fl524.pdf` | 117 | 1340 | 1459 | `native_plus_ocr` |

Falta rodar em um PDF real difícil fornecido ou aprovado pelo defensor.
