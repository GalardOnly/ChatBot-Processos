# ChatBot Processos

O ChatBot Processos e uma PoC de uma ferramenta criada para ajudar defensores publicos a analisar processos judiciais em PDF e se preparar melhor para audiencias.

Nesta versao inicial, o defensor envia o PDF completo do processo, o sistema extrai e organiza o conteudo por pagina, cria uma base de busca vetorial e permite conversar com o processo por meio de um chat. As respostas sao geradas a partir dos trechos recuperados no proprio documento e exibem as paginas usadas como fonte, para que o defensor consiga conferir rapidamente de onde saiu cada informacao.

## Status

O projeto esta em fase de Prova de Conceito. A intencao neste momento nao e entregar um produto final, mas validar se a ideia principal funciona na pratica: receber um processo real, extrair o texto com referencias de pagina, recuperar os trechos mais importantes e responder perguntas de forma util para a preparacao de audiencia.

A PoC ja funciona localmente com upload de PDF, extracao de texto por pagina usando PyMuPDF, OCR para paginas escaneadas ou com pouco texto, divisao do conteudo em chunks, armazenamento local em SQLite, indexacao vetorial com ChromaDB, recuperacao semantica com ensemble juridico, chat com Gemini como modelo principal, Groq como fallback, triagem juridica interna das perguntas, interface simples em Streamlit e testes automatizados.

Em um teste local com um PDF real de aproximadamente 14 MB, a aplicacao processou 105 paginas e gerou 149 chunks pesquisaveis.

## Objetivo da PoC

O objetivo da PoC e validar se e possivel transformar um processo judicial em PDF em uma experiencia de consulta realmente util para o defensor publico. A ferramenta nao substitui a analise juridica, nao toma decisoes pelo profissional e nao deve ser tratada como fonte definitiva. Ela serve para organizar informacoes, recuperar trechos relevantes, sugerir pontos de atencao e acelerar a leitura dirigida do processo, sempre exigindo revisao humana.

O [mapa mental e registro de decisoes](docs/28-mapa-mental-e-decisoes.md) explica por que a arquitetura atual foi escolhida, quais alternativas existiam e o que deve ser mantido ou substituido antes de um produto comercial.

## Fluxo principal

O fluxo principal comeca quando o defensor envia o PDF do processo pela interface. O backend extrai o texto pagina por pagina e, quando encontra paginas ruins ou escaneadas, pode acionar OCR para tentar recuperar o conteudo. Depois disso, o texto e dividido em blocos menores, mantendo a pagina de origem de cada trecho. Esses blocos sao indexados no ChromaDB para permitir busca semantica.

Quando o defensor faz uma pergunta, a aplicacao busca os trechos mais relevantes daquele processo, envia esse contexto para a LLM e retorna uma resposta baseada nas fontes encontradas. A resposta tambem mostra as paginas e os trechos usados, permitindo que o usuario confira a informacao diretamente no documento original.

## Recuperacao juridica

O projeto usa recuperacao hibrida. O componente semantico `legal-ensemble` combina sinais dos modelos juridicos JurisBERT e Legal-BERTimbau, enquanto uma busca lexical local reforca datas, numeros, resultados e outras expressoes exatas. O BERTikal continua disponivel para testes isolados, mas saiu do ensemble padrao depois dos primeiros benchmarks. Esses modelos nao respondem diretamente ao usuario. A funcao deles e ajudar a encontrar quais trechos do processo parecem mais relevantes para uma pergunta.

Na pratica, eles atuam antes da LLM. Primeiro, a pergunta do defensor e comparada com os chunks do processo. Depois, os trechos mais promissores sao selecionados e enviados para o modelo gerador. Assim, Gemini e Groq ficam responsaveis pela resposta final, enquanto os modelos juridicos ajudam na recuperacao do contexto correto.

## Triagem interna das perguntas

O defensor escreve a pergunta com as proprias palavras. Antes da busca, o sistema tenta relacionar essa pergunta com guias juridicos oficiais e candidatos previamente catalogados. Essa classificacao nao aparece como uma lista de botoes e nao substitui a pergunta original. Quando a correspondencia e forte, os termos do guia funcionam como um reforco para localizar trechos relevantes e como contexto de organizacao para a LLM.

Perguntas vagas ou sem correspondencia juridica segura seguem para a busca sem enriquecimento. Nas perguntas classificadas, o recuperador combina os resultados da pergunta original com os resultados da versao enriquecida, dando mais peso ao texto escrito pelo defensor. Isso reduz o risco de um guia inadequado desviar a consulta.

## LLMs

O modelo principal de resposta e o `gemini:gemini-3-flash-preview`, escolhido porque nos testes iniciais apresentou respostas mais organizadas e mais confortaveis de ler. O `groq:llama-3.1-8b-instant` fica como fallback para manter o chat funcionando caso o provedor principal falhe ou fique indisponivel.

## Interface

A interface atual foi feita em Streamlit para manter a PoC simples e rapida de testar. Ela permite subir um PDF, acompanhar o processamento, conversar livremente com o processo e visualizar as fontes recuperadas.

O banco de perguntas juridicas atua nos bastidores. O usuario nao precisa escolher entre dezenas de perguntas prontas nem entender a classificacao interna. A intencao e preservar uma experiencia de chat simples enquanto a aplicacao usa as referencias oficiais para compreender melhor o objetivo da consulta.

## Benchmark do roteamento

O roteamento interno foi comparado com a pergunta bruta em 50 consultas deterministicas geradas a partir de um processo real de 105 paginas. Com a recuperacao hibrida, o hit rate ficou em `0,84` nas duas variantes e o MRR passou de `0,5247` para `0,5347`. Dois casos melhoraram, um piorou e 47 empataram.

Uma nova suite multidominio usa tres acordaos publicos do STJ, nas areas de familia, violencia domestica e saude suplementar, com dez perguntas e paginas esperadas. Nela, o hit rate passou de `0,90` para `1,00`, o MRR passou de `0,6450` para `0,6733` e nenhum caso piorou. Os dez casos ainda aguardam revisao profissional, portanto o resultado valida a recuperacao tecnica, nao a qualidade juridica final.

## Estrutura

```text
backend/
  streamlit_app.py
  src/preparador_audiencia/
    api.py
    benchmark.py
    benchmark_cli.py
    chat.py
    chunking.py
    database.py
    embeddings.py
    ensemble.py
    ingestion.py
    lexical_search.py
    llm.py
    ocr.py
    pdf_extraction.py
    quality.py
    question_router.py
    reference_benchmark.py
    reference_suite.py
    reference_suite_cli.py
    repositories.py
    retrieval.py
    routing_benchmark.py
    routing_benchmark_cli.py
    search.py
    settings.py
    vector_store.py
  tests/
docs/
```

## Instalar

Para instalar o projeto localmente, entre na pasta do backend e instale as dependencias de desenvolvimento e modelos.

```powershell
cd backend
python -m pip install -e .[dev,models]
```

Tambem e necessario criar um arquivo local `backend/.env` com as chaves e configuracoes usadas pela aplicacao. Esse arquivo e apenas local e nao deve ser enviado para o Git.

```text
GEMINI_API_KEY=sua-chave
GROQ_API_KEY=sua-chave
PREPARADOR_EMBEDDING_PROVIDER=legal-ensemble
```

O arquivo `.env` nao deve ser versionado.

## Rodar localmente

Para rodar localmente, suba primeiro a API em um terminal.

```powershell
cd backend
python -m uvicorn preparador_audiencia.main:app --host localhost --port 8910
```

Depois, em outro terminal, suba a interface Streamlit.

```powershell
cd backend
python -m streamlit run streamlit_app.py --server.address localhost --server.port 8501
```

Com os dois servicos rodando, a interface fica disponivel em `http://localhost:8501` e a documentacao da API em `http://localhost:8910/docs`.

O uso de `localhost` indica que a aplicacao esta rodando somente na propria maquina de desenvolvimento.

## Testes

Os testes e a verificacao de estilo podem ser executados na raiz do projeto.

```powershell
python -m pytest
python -m ruff check .
```

## Limitacoes atuais

Esta PoC ainda nao e um produto pronto para producao. A interface ainda e simples, a primeira busca com modelos BERT pode ser lenta e ainda faltam pontos importantes como autenticacao, controle de usuarios, politica de dados e LGPD, logging estruturado, deploy e validacao com defensores em uso real. Os casos automaticos do benchmark usam as paginas e os termos do proprio processo como referencia, portanto nao substituem um conjunto de perguntas e respostas revisado por profissionais.

## Proximo passo

O proximo passo recomendado e revisar com um profissional os dez casos da suite multidominio e acrescentar respostas de referencia. Depois disso, o benchmark deve avaliar as respostas geradas por fidelidade as fontes, completude, utilidade para audiencia e risco de alucinacao, sem usar a LLM como unica avaliadora.
