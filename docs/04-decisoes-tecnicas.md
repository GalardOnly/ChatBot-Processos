# Decisoes Tecnicas Iniciais

## Estrutura do Repositorio

Comecar em monorepo local:

- `backend/`;
- `frontend/`;
- `docs/`;
- `samples/`;
- `scripts/`.

## Organizacao do Codigo

Evitar um arquivo central gigante. Cada responsabilidade deve ficar em um modulo
proprio:

- `main.py`: criacao do app FastAPI e montagem de roteadores;
- `api.py`: rotas HTTP e validacoes de entrada/saida;
- `database.py`: conexao e schema do SQLite;
- `repositories.py`: consultas e persistencia;
- `pdf_extraction.py`: extracao com PyMuPDF;
- `ocr.py`: OCR local;
- `chunking.py`: divisao do texto por pagina em trechos;
- `embeddings.py`: providers de embeddings;
- `vector_store.py`: integracao com ChromaDB;
- `search.py`: orquestracao de indexacao e busca.

Essa separacao deve continuar nas proximas fases. Chat/LLM, sessao, admin,
autenticacao e interface nao devem ser misturados nas rotas principais.

## Backend

- Python;
- FastAPI;
- PyMuPDF para extracao de PDF;
- RapidOCR/ONNXRuntime como OCR local para paginas escaneadas;
- SQLite no v0.1;
- ChromaDB para vetores;
- processamento assincrono simples;
- pytest;
- Ruff.

## Frontend

- Streamlit no v0.1, pela velocidade de validacao;
- migracao para React fica para depois da validacao do fluxo.

## IA

- embeddings para busca semantica no processo;
- ChromaDB com colecao por processo;
- BERTikal (`felipemaiapolo/legalnlp-bert`) como provider juridico configuravel;
- provider `hash` apenas para desenvolvimento, testes e ambientes sem modelo carregado;
- Groq para resposta via LLM;
- prompt restrito aos trechos recuperados;
- resposta sempre com paginas citadas;
- fallback obrigatorio quando nao houver fonte suficiente.

## Endpoints Fixos do v0.1

- `POST /upload`;
- `GET /processo/{id}/status`;
- `POST /processo/{id}/chat`.

## Endpoints Tecnicos de Validacao

- `POST /processo/{id}/buscar`: valida a busca vetorial antes de ligar a LLM.

## Decisao Critica

O primeiro teste tecnico sera extracao com PDF real dificil. Nao vale avancar
para chat, embeddings ou interface sem saber se o texto extraido por pagina e
minimamente confiavel.

## Termos de UI

Usar:

- processo;
- pagina;
- trecho;
- fonte;
- resposta;
- pergunta.

Evitar na UI:

- chunk;
- embedding;
- vetor;
- ChromaDB;
- payload;
- prompt.
