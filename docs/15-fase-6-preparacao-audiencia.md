# Fase 6: Preparacao de audiencia guiada

## Objetivo

Reduzir a dependencia de o usuario saber quais perguntas fazer. A interface passa
a sugerir perguntas juridicamente uteis e tambem gera um roteiro de audiencia por
blocos.

## Entrega

Na aba `Chat`:

- perguntas sugeridas em botoes;
- cada pergunta usa o endpoint `/processo/{id}/chat`;
- as respostas continuam trazendo fontes recuperadas.

Na aba `Preparacao de audiencia`:

- botao `Gerar roteiro de audiencia`;
- geracao de seis blocos:
  - resumo do caso;
  - linha do tempo;
  - provas e documentos;
  - pontos controvertidos;
  - perguntas sugeridas;
  - checklist final.

## Observacao de custo

O roteiro completo faz uma chamada de LLM por bloco. Na configuracao atual, o
Gemini e o modelo principal e o Groq entra apenas como fallback.

## Como testar

1. Abra `http://127.0.0.1:8501`.
2. Carregue o ultimo processo concluido na barra lateral.
3. Use os botoes de perguntas sugeridas na aba `Chat`.
4. Abra a aba `Preparacao de audiencia`.
5. Clique em `Gerar roteiro de audiencia`.

## Criterio de pronto

- usuario sem conhecimento juridico consegue iniciar testes;
- o defensor recebe uma preparacao inicial estruturada;
- cada bloco mantem fontes para revisao humana.
