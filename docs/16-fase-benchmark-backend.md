# Fase de Benchmark Backend

Esta fase cria uma forma mais objetiva de evoluir a PoC sem depender imediatamente de feedback juridico frequente.

O benchmark sera dividido em dois caminhos. O primeiro usa datasets de recuperacao juridica, como o JurisTCU, para medir se o sistema encontra documentos ou trechos relevantes para uma pergunta. Esse caminho e bom para comparar recuperadores, embeddings e estrategias de ranking, porque ja existe uma base com consultas e julgamentos de relevancia.

O segundo caminho usa PDFs publicos ou anonimizados. Esse caminho e mais proximo do produto real, porque testa a cadeia completa: download local da amostra, extracao com PyMuPDF, OCR quando necessario, chunking, indexacao, busca e resposta com fontes.

No momento, o projeto ganhou um manifesto em `backend/benchmark_sources.example.json`. Ele registra fontes candidatas encontradas na pesquisa, incluindo datasets e PDFs/HTMLs publicos. Os arquivos baixados para teste devem ficar em `samples/benchmark/`, pasta local ignorada pelo Git.

Comandos iniciais:

```powershell
cd backend
benchmark-fontes listar
benchmark-fontes listar --kind pdf
benchmark-fontes baixar-pdfs
```

Depois que um PDF candidato for baixado, ele pode ser enviado pela interface Streamlit ou pela API normal de upload. Em seguida, criamos um arquivo `cases.json` com perguntas, paginas esperadas e termos esperados. A avaliacao dos modelos continua usando:

```powershell
cd backend
avaliar-poc-modelos --processo-id proc_xxxxx --cases reports/meus-casos.json --embedding legal-ensemble --llm-model gemini:gemini-3-flash-preview
```

Fontes iniciais escolhidas:

JurisTCU no Hugging Face, por ser um dataset brasileiro de recuperacao de informacao juridica com documentos, consultas e julgamentos de relevancia.

Awesome Legal Data, por ser um catalogo comunitario para descobrir novas bases juridicas abertas.

Jusbrasil, como fonte nao oficial de decisoes publicas e exemplos de experiencia de produto, sempre respeitando os termos do provedor.

PDFs hospedados por Global Freedom of Expression/Columbia e Poder360, por conterem documentos digitalizados de processos do STJ e servirem como amostras ruins para OCR e pagina de origem.

Datajud e Arquivo Nacional, como fontes oficiais complementares. O Datajud ajuda com metadados, mas nao entrega os PDFs dos autos. O Arquivo Nacional pode fornecer processos historicos, uteis para testar extracao, embora nao representem perfeitamente a rotina atual de audiencia.

O criterio de pronto desta fase e conseguir rodar benchmark em pelo menos tres amostras locais: uma baseada em dataset de recuperacao, uma em PDF oficial e uma em PDF nao oficial ou hospedado por agregador/imprensa.

## Resultado inicial com JurisTCU

Foi criado o comando `benchmark-fontes juristcu` para rodar avaliacao de recuperacao no dataset JurisTCU do Hugging Face.

Rodada baseline, sem LLM e sem custo externo:

```powershell
cd backend
python -m preparador_audiencia.benchmark_cli juristcu --queries 20 --distractors 1000 --embedding hash --top-k 10 --output reports\juristcu-hash-q20-d1000.json
```

Resultado:

Hit rate: `0.6500`

MRR: `0.5030`

Precisao media no Top K: `0.2300`

Rodadas pequenas para comparar os tres embeddings juridicos:

```powershell
cd backend
python -m preparador_audiencia.benchmark_cli juristcu --queries 5 --distractors 250 --embedding legal-bertimbau --top-k 10 --output reports\juristcu-legal-bertimbau-q5-d250.json
python -m preparador_audiencia.benchmark_cli juristcu --queries 5 --distractors 250 --embedding bertikal --top-k 10 --output reports\juristcu-bertikal-q5-d250.json
python -m preparador_audiencia.benchmark_cli juristcu --queries 5 --distractors 250 --embedding jurisbert --top-k 10 --output reports\juristcu-jurisbert-q5-d250.json
```

Resultado no recorte de 5 consultas e 312 documentos indexados:

Legal-BERTimbau: hit rate `1.0000`, MRR `1.0000`, precisao media no Top K `0.7800`.

JurisBERT: hit rate `1.0000`, MRR `1.0000`, precisao media no Top K `0.7600`.

BERTikal: hit rate `1.0000`, MRR `0.6067`, precisao media no Top K `0.3200`.

Leitura inicial: neste recorte pequeno, Legal-BERTimbau e JurisBERT foram claramente superiores ao baseline hash e ao BERTikal. O resultado ainda nao decide o modelo final, porque precisamos rodar mais consultas e testar a combinacao dos melhores modelos em ensemble no mesmo benchmark.

## Benchmark maior e ajuste do ensemble

Depois da primeira rodada, o `legal-ensemble` padrao foi ajustado para usar apenas:

`jurisbert`

`legal-bertimbau`

O BERTikal saiu do ensemble padrao porque ficou bem abaixo dos outros dois no recorte inicial. Ele continua disponivel para testes isolados.

Rodadas maiores com 20 consultas, 1000 distraidores e 1245 documentos indexados:

Hash baseline: hit rate `0.6500`, MRR `0.5030`, precisao media no Top K `0.2300`.

Legal-BERTimbau: hit rate `0.9000`, MRR `0.7333`, precisao media no Top K `0.4050`.

JurisBERT: hit rate `0.9500`, MRR `0.7137`, precisao media no Top K `0.3300`.

Legal ensemble, usando JurisBERT e Legal-BERTimbau: hit rate `1.0000`, MRR `0.7109`, precisao media no Top K `0.4150`.

Leitura: o ensemble novo teve a melhor cobertura e a melhor precisao media no Top K. O Legal-BERTimbau isolado teve MRR ligeiramente melhor, ou seja, em algumas consultas colocou o primeiro documento relevante mais cedo. Para a PoC, o melhor padrao continua sendo `legal-ensemble`, porque reduz a chance de nao recuperar nenhuma fonte relevante.

## Risco de vicio em um dataset

Testar apenas no JurisTCU nao prova que o sistema esta pronto para processos reais de audiencia. O modelo pode ficar otimizado demais para o estilo de documentos do TCU, para os temas de licitacao/controle externo e para o formato de consulta desse dataset.

Por isso, o JurisTCU deve ser usado como benchmark tecnico de recuperacao, nao como prova final de qualidade juridica do produto. O proximo passo e manter pelo menos tres familias de teste:

JurisTCU para recuperacao juridica objetiva com qrels.

PDFs publicos digitalizados para OCR, pagina de origem e robustez de extracao.

Casos reais anonimizados ou revisados por defensor/promotor quando houver disponibilidade, para medir utilidade em audiencia.

A suite operacional dessas tres familias esta documentada em `docs/18-suite-qualidade-juridica.md`.
