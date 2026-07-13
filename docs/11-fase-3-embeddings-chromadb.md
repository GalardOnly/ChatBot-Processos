# Fase 3: Embeddings e ChromaDB

## Objetivo

Transformar os trechos extraidos do processo em vetores e permitir busca por
pergunta, preservando pagina, indice do trecho e tipo de documento.

## Implementado

- interface `EmbeddingProvider`;
- provider real `BertikalEmbeddingProvider` usando mean pooling;
- provider local `HashEmbeddingProvider` para testes e desenvolvimento;
- armazenamento vetorial persistente em ChromaDB;
- indexacao automatica ao final da ingestao;
- rota `POST /processo/{id}/buscar` para validar recuperacao sem LLM.

## Configuracao

Desenvolvimento:

```powershell
$env:PREPARADOR_EMBEDDING_PROVIDER="hash"
```

BERTikal:

```powershell
python -m pip install -e .[bertikal]
$env:PREPARADOR_EMBEDDING_PROVIDER="bertikal"
$env:PREPARADOR_EMBEDDING_MODEL="felipemaiapolo/legalnlp-bert"
```

ChromaDB:

```powershell
$env:PREPARADOR_CHROMA_DIR="C:\caminho\chroma"
```

## Criterio de validacao

Ao perguntar por audiencia, prazo, decisao ou medida protetiva, a rota de busca
deve devolver trechos do processo que mencionem diretamente o assunto e sempre
informar a pagina de origem.

## Proximo passo

A Fase 4 deve ligar essa recuperacao ao Groq, criando `POST /processo/{id}/chat`
com resposta baseada apenas nas fontes recuperadas.
