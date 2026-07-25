# ChatBot Processos

O ChatBot Processos e uma PoC de uma ferramenta criada para ajudar defensores publicos a analisar processos judiciais em PDF e se preparar melhor para audiencias.

Nesta versao inicial, o defensor envia o PDF completo do processo, o sistema extrai e organiza o conteudo por pagina, cria uma base de busca vetorial e permite conversar com o processo por meio de um chat. As respostas sao geradas a partir dos trechos recuperados no proprio documento e exibem as paginas usadas como fonte, para que o defensor consiga conferir rapidamente de onde saiu cada informacao.

## Status

O projeto esta em fase de Prova de Conceito. A intencao neste momento nao e entregar um produto final, mas validar se a ideia principal funciona na pratica: receber um processo real, extrair o texto com referencias de pagina, recuperar os trechos mais importantes e responder perguntas de forma util para a preparacao de audiencia.

A PoC ja funciona localmente com upload de PDF, extracao de texto por pagina usando PyMuPDF, OCR para paginas escaneadas ou com pouco texto, divisao do conteudo em chunks, armazenamento local em SQLite, indexacao vetorial com ChromaDB, recuperacao semantica com ensemble juridico, chat com Gemini como modelo principal, Groq como fallback, interface simples em Streamlit, botoes de preparacao para audiencia e testes automatizados.

Em um teste local com um PDF real de aproximadamente 14 MB, a aplicacao processou 105 paginas e gerou 149 chunks pesquisaveis.

## Objetivo da PoC

O objetivo da PoC e validar se e possivel transformar um processo judicial em PDF em uma experiencia de consulta realmente util para o defensor publico. A ferramenta nao substitui a analise juridica, nao toma decisoes pelo profissional e nao deve ser tratada como fonte definitiva. Ela serve para organizar informacoes, recuperar trechos relevantes, sugerir pontos de atencao e acelerar a leitura dirigida do processo, sempre exigindo revisao humana.

## Fluxo principal

O fluxo principal comeca quando o defensor envia o PDF do processo pela interface. O backend extrai o texto pagina por pagina e, quando encontra paginas ruins ou escaneadas, pode acionar OCR para tentar recuperar o conteudo. Depois disso, o texto e dividido em blocos menores, mantendo a pagina de origem de cada trecho. Esses blocos sao indexados no ChromaDB para permitir busca semantica.

Quando o defensor faz uma pergunta, a aplicacao busca os trechos mais relevantes daquele processo, envia esse contexto para a LLM e retorna uma resposta baseada nas fontes encontradas. A resposta tambem mostra as paginas e os trechos usados, permitindo que o usuario confira a informacao diretamente no documento original.

## Recuperacao juridica

O projeto usa um recuperador chamado `legal-ensemble`, pensado para combinar sinais dos modelos juridicos JurisBERT e Legal-BERTimbau. O BERTikal continua disponivel para testes isolados, mas saiu do ensemble padrao depois dos primeiros benchmarks. Esses modelos nao respondem diretamente ao usuario. A funcao deles e ajudar a encontrar quais trechos do processo parecem mais relevantes para uma pergunta.

Na pratica, eles atuam antes da LLM. Primeiro, a pergunta do defensor e comparada com os chunks do processo. Depois, os trechos mais promissores sao selecionados e enviados para o modelo gerador. Assim, Gemini e Groq ficam responsaveis pela resposta final, enquanto os modelos juridicos ajudam na recuperacao do contexto correto.

## LLMs

O modelo principal de resposta e o `gemini:gemini-3-flash-preview`, escolhido porque nos testes iniciais apresentou respostas mais organizadas e mais confortaveis de ler. O `groq:llama-3.1-8b-instant` fica como fallback para manter o chat funcionando caso o provedor principal falhe ou fique indisponivel.

## Interface

A interface atual foi feita em Streamlit para manter a PoC simples e rapida de testar. Ela permite subir um PDF, acompanhar o processamento, conversar com o processo, visualizar as fontes recuperadas e usar botoes com perguntas prontas voltadas para a rotina de preparacao de audiencia.

Hoje a interface ja inclui atalhos como preparar audiencia, gerar perguntas para a parte assistida, levantar pontos para contraditar, identificar documentos que precisam ser abertos, apontar riscos e urgencias e produzir um resumo rapido de dois minutos. Esses botoes ainda devem ser validados com defensores em uso real, porque a utilidade deles depende diretamente da rotina de trabalho de quem atua em audiencia.

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
    llm.py
    ocr.py
    pdf_extraction.py
    quality.py
    repositories.py
    retrieval.py
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

Esta PoC ainda nao e um produto pronto para producao. A interface ainda e simples, PDFs grandes podem demorar para processar, a primeira busca com modelos BERT pode ser lenta e ainda faltam pontos importantes como autenticacao, controle de usuarios, politica de dados e LGPD, logging estruturado, deploy e validacao com defensores em uso real.

## Proximo passo

O proximo passo recomendado e mostrar a PoC para um defensor publico, coletar feedback real e ajustar os botoes, prompts e roteiro de preparacao conforme a rotina dele. A partir desse retorno, o projeto pode evoluir com mais seguranca para uma versao menos experimental e mais proxima de um produto utilizavel.
