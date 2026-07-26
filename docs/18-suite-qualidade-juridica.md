# Suite de Qualidade Juridica

Esta fase organiza a validacao da PoC em tres familias de teste. A ideia e evitar que o projeto fique bom apenas em um dataset e ruim no uso real.

## Familia 1: JurisTCU

Objetivo: medir recuperacao juridica com uma base que ja possui consultas e documentos relevantes esperados.

Uso:

```powershell
cd backend
python -m preparador_audiencia.benchmark_cli juristcu --queries 20 --distractors 1000 --embedding legal-ensemble --top-k 10 --output reports\juristcu-legal-ensemble-q20-d1000.json
```

Resultado atual do `legal-ensemble`, usando JurisBERT e Legal-BERTimbau:

Hit rate: `1.0000`

MRR: `0.7109`

Precisao media no Top K: `0.4150`

Leitura: bom para medir se a busca encontra algum documento juridicamente relevante. Nao mede OCR, pagina de processo nem utilidade de audiencia.

O benchmark do JurisTCU reaproveita indices existentes no ChromaDB quando a mesma combinacao de consultas, distraidores e embedding ja foi indexada antes. Isso evita recalcular embeddings de milhares de documentos em rodadas repetidas. Para forcar recriacao dos indices, use `--reindex`.

```powershell
cd backend
python -m preparador_audiencia.benchmark_cli juristcu --queries 100 --distractors 1000 --embedding legal-ensemble --top-k 10 --reindex
```

## Familia 2: PDFs publicos digitalizados

Objetivo: medir robustez de PDF, texto nativo, OCR, paginas com imagem e tempo de extracao.

Uso sem OCR:

```powershell
cd backend
python -m preparador_audiencia.benchmark_cli pdfs ..\samples\benchmark\*.pdf --family pdfs-publicos --no-ocr --output reports\pdfs-publicos-sem-ocr.json
```

Resultado sem OCR:

`hc-312561.pdf`: 3 paginas, 4752 caracteres, 0 paginas com OCR.

`processo-direito-ao-esquecimento.pdf`: 83 paginas, 10765 caracteres, 83 paginas com imagem.

`Silviera-Complaint.pdf`: 32 paginas, 4364 caracteres, 32 paginas com imagem.

Uso com OCR limitado:

```powershell
cd backend
python -m preparador_audiencia.benchmark_cli pdfs ..\samples\benchmark\*.pdf --family pdfs-publicos-ocr-amostra --max-pages 5 --output reports\pdfs-publicos-ocr-5p.json
```

Resultado com OCR nas primeiras paginas:

`hc-312561.pdf`: 3 paginas, 4752 caracteres, 0 paginas com OCR.

`processo-direito-ao-esquecimento.pdf`: 5 paginas, 5211 caracteres, 4 paginas com OCR.

`Silviera-Complaint.pdf`: 5 paginas, 4536 caracteres, 4 paginas com OCR.

Leitura: os PDFs maiores tem imagem em todas as paginas e dependem bastante de OCR. Esse e o tipo de teste que o JurisTCU nao cobre.

## Familia 3: PDFs reais anonimizados

Objetivo: medir utilidade real para audiencia.

Os PDFs dessa familia devem ficar apenas em `samples/anonimizados/`, pasta ignorada pelo Git. O arquivo de casos pode partir de `backend/benchmark_cases.anonimizado.example.json`.

O fluxo recomendado e:

1. Anonimizar ou usar um processo autorizado.
2. Colocar o PDF em `samples/anonimizados/`.
3. Rodar extracao com OCR limitado para conferir qualidade.
4. Subir o PDF pela API ou Streamlit.
5. Preencher paginas esperadas e termos esperados no arquivo de casos.
6. Rodar `avaliar-poc-modelos` com `legal-ensemble`.
7. Rodar algumas perguntas com `avaliar: true` para testar a LLM avaliadora.

Essa familia e a mais importante para decidir produto, mas so deve entrar quando houver seguranca de dados e autorizacao.

## Regra de decisao

O JurisTCU decide se a busca semantica esta melhorando.

Os PDFs publicos decidem se a extracao e o OCR aguentam documento ruim.

Os PDFs anonimizados decidem se a ferramenta ajuda na preparacao de audiencia.

Nenhuma familia sozinha decide a qualidade do produto.
