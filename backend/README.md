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

O ambiente local aceita PDFs de ate 200 MB por padrao. O limite pode ser
alterado com `PREPARADOR_MAX_UPLOAD_MB`. O encaminhamento de portas do VS Code
usa Microsoft Dev Tunnels, cujo limite atual e 16 MB por requisicao HTTP.
Por isso, processos maiores devem ser enviados pelo endereco local; depois de
processados, o resultado pode ser consultado normalmente pelo endereco publico.

## Processamento de PDFs grandes

O upload identifica o arquivo pelo hash SHA-256. Quando o mesmo PDF ja foi
processado, o resultado existente e carregado sem repetir extracao, OCR ou
embeddings. Se ele ja estiver na fila, um segundo envio tambem reutiliza o
mesmo processamento.

Durante um processamento novo, o endpoint de status informa a etapa, a
mensagem e o percentual concluido. A interface atualiza esses dados
automaticamente. O OCR trabalha em lotes pequenos com duas sessoes
independentes e os embeddings sao gerados em lotes para limitar memoria e
manter a maquina responsiva.

Os valores podem ser ajustados pela configuracao:

```powershell
$env:PREPARADOR_OCR_ZOOM="1.5"
$env:PREPARADOR_OCR_WORKERS="2"
$env:PREPARADOR_EMBEDDING_BATCH_SIZE="16"
$env:PREPARADOR_EMBEDDING_DEVICE="auto"
$env:PREPARADOR_MAX_UPLOAD_MB="200"
```

Com `auto`, os modelos de embedding usam CUDA quando o PyTorch e uma GPU
compativel estao disponiveis; caso contrario, continuam na CPU. Use `cpu` para
forcar o processador ou `cuda:0` para escolher explicitamente a primeira GPU.

Na maquina com GPU NVIDIA, instale a distribuicao CUDA usada pela PoC:

```powershell
python -m pip install torch==2.11.0+cu128 --index-url https://download.pytorch.org/whl/cu128
```

No PDF real de referencia com 14,9 MB e 105 paginas, sendo 39 submetidas a
OCR, a extracao caiu de aproximadamente 242 para 133 segundos no ambiente
local usado pela PoC. JurisBERT e Legal-BERTimbau acrescentaram cerca de 57
segundos na primeira carga. Reenvios do mesmo PDF passam a ser praticamente
imediatos.

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

## Benchmark de respostas

Depois de escolher o recuperador padrao, o proximo teste importante e avaliar o
fluxo completo. Nesse modo, o sistema indexa o processo no recuperador escolhido,
recupera fontes com o `legal-ensemble`, pede ao Gemini para responder e usa o
Groq como avaliador auxiliar da qualidade juridica da resposta.

Antes de rodar valendo, confira o plano:

```powershell
benchmark-respostas `
  --processo-id proc_xxxxx `
  --cases benchmark_cases.hc-312561.example.json `
  --embedding legal-ensemble `
  --top-k 5 `
  --dry-run
```

Para uma amostra pequena e barata, limite a quantidade de perguntas:

```powershell
benchmark-respostas `
  --processo-id proc_xxxxx `
  --cases benchmark_cases.hc-312561.example.json `
  --embedding legal-ensemble `
  --limit-cases 1 `
  --max-llm-calls 3 `
  --output reports/benchmark-respostas-amostra.json
```

Para executar uma bateria com os tres casos do exemplo:

```powershell
benchmark-respostas `
  --processo-id proc_xxxxx `
  --cases benchmark_cases.hc-312561.example.json `
  --embedding legal-ensemble `
  --top-k 5 `
  --max-llm-calls 9 `
  --output reports/benchmark-respostas.json
```

O comando considera uma estimativa conservadora de chamadas: gerador principal,
fallback possivel e avaliador para cada pergunta. Ele gera um JSON completo e um
Markdown resumido com fidelidade as fontes, completude juridica, utilidade para
audiencia e risco de alucinacao. O relatorio tambem mostra sinais objetivos por
regra, como paginas citadas, paginas citadas fora das fontes e proporcao de
linhas afirmativas com citacao.

## Banco de perguntas para audiencia

A PoC tambem possui um banco inicial de perguntas para orientar testes e ajudar o
defensor a explorar o processo pelo chat. As perguntas sao separadas por area,
tipo de audiencia, tags e prioridade.

Para listar perguntas no terminal:

```powershell
perguntas-audiencia --area criminal --tag custodia --limit 3
```

Para exportar perguntas em formato compativel com o benchmark de respostas:

```powershell
perguntas-audiencia `
  --area geral `
  --limit 6 `
  --format cases-json `
  --output reports/perguntas-gerais.cases.json
```

A API tambem expoe esse banco em `GET /perguntas-audiencia`, com filtros
opcionais `area`, `audiencia`, `tag` e `limit`.

## Perguntas candidatas

O banco oficial e intencionalmente revisado. Para aumentar escala sem perder
rastreabilidade, a PoC possui uma curadoria de fontes em
`data/question_sources.json` e um gerador deterministico de perguntas
candidatas. Essas perguntas carregam origem, URL, tipo de fonte e status
`candidate`.

Para listar candidatas de audiencia de custodia:

```powershell
perguntas-candidatas --area criminal --audiencia custodia --official-only --limit 12
```

Para exportar candidatas em formato compativel com o benchmark:

```powershell
perguntas-candidatas `
  --area familia `
  --format cases-json `
  --output reports/perguntas-familia-candidatas.cases.json
```

As candidatas nao aparecem automaticamente como perguntas oficiais. Elas devem
ser revisadas ou testadas antes de serem promovidas para o banco principal.

Para criar um arquivo de revisao e promover apenas perguntas aprovadas:

```powershell
perguntas-promocao criar-revisao `
  --area criminal `
  --audiencia custodia `
  --official-only `
  --limit 20 `
  --output reports/revisao-custodia.json
```

Depois de alterar `decision` para `approved` nas perguntas escolhidas:

```powershell
perguntas-promocao promover --review reports/revisao-custodia.json
```

As aprovadas entram em `data/approved_question_templates.json` e passam a ser
lidas por `perguntas-audiencia`, pelo endpoint `GET /perguntas-audiencia` e pelo
roteador interno do chat.

Na interface Streamlit, o defensor escreve livremente. O backend usa perguntas
oficiais e candidatas como uma camada interna de triagem, classificacao e
ranking. Essa camada enriquece a busca vetorial e orienta o prompt enviado ao
LLM, mas nao aparece como lista de botoes na tela.

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

## Suite de referencia multidominio

A suite versionada em `data/reference_suite_multidomain.json` descreve tres
acordaos publicos do STJ, seus hashes e dez casos de recuperacao. Os PDFs ficam
fora do Git e podem ser baixados das URLs oficiais registradas no manifesto.

Para validar apenas o schema e os gabaritos:

```powershell
suite-referencia validar
```

Para baixar os documentos ausentes, processar os PDFs e executar o benchmark sem
chamadas de LLM:

```powershell
suite-referencia executar `
  --download-missing `
  --status pending `
  --top-k 5 `
  --embedding legal-ensemble `
  --output reports/benchmark-referencia-multidominio.json
```

Os estados `pending`, `in_review` e `approved` permitem separar conferencia
tecnica de aprovacao juridica. O resultado atual nao deve ser apresentado como
validacao profissional enquanto os casos permanecerem pendentes.
