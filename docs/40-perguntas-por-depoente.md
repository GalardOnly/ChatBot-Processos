# Perguntas para audiencia por depoente

## Objetivo

Esta fase transforma a fala literal de uma pessoa em um roteiro curto de
perguntas para audiencia. O roteiro pode considerar contradicoes potenciais ja
comparadas, mas nao apresenta uma divergencia como mentira nem como conclusao
juridica.

## Fluxo

O usuario escolhe um depoimento identificado. O backend carrega a transcricao
3.0 e exige que o corpo da fala tenha inicio e fim confirmados. As comparacoes
mais recentes relacionadas a essa pessoa tambem podem ser incluidas.

Gemini gera a primeira versao do roteiro. Groq e usado somente quando Gemini
falha ou devolve um formato invalido. O resultado e persistido para evitar novas
chamadas desnecessarias.

Cada pergunta possui tema, objetivo, tipo, prioridade e um ou mais trechos de
apoio. Os tipos atuais sao esclarecimento, cronologia, percepcao, confirmacao e
contradicao potencial.

## Validacao das fontes

A LLM precisa copiar um trecho exato e informar o identificador da fonte que
motivou cada pergunta. O servidor confirma a citacao e vincula a pagina real.
Perguntas sem apoio literal sao descartadas.

Uma pergunta classificada como contradicao potencial precisa de trechos de dois
depoimentos diferentes. Um unico trecho nao basta para sustentar esse tipo.

O conteudo das falas e tratado como fonte nao confiavel. Se o filtro
deterministico encontrar formato de prompt injection, o texto nao e enviado a
LLM.

## Persistencia

O cache considera o processo, o depoimento, a versao da transcricao e o conjunto
de comparacoes utilizadas. Quando uma comparacao nova e incorporada, um novo
roteiro e gerado. O parametro `regenerar` permite refazer o mesmo roteiro de
forma explicita.

O reprocessamento dos chunks apaga transcricoes, comparacoes e roteiros antigos
na mesma operacao.

## Endpoints

`POST /processo/{id}/depoimentos/{depoimento_id}/perguntas-audiencia` recebe
`max_perguntas`, entre 3 e 15, e `regenerar`.

`GET /processo/{id}/perguntas-audiencia/{roteiro_id}` recupera um roteiro
persistido.

## Limites

O roteiro organiza a preparacao e nao substitui a conducao profissional da
audiencia. O defensor pode mudar a ordem, reformular, retirar ou acrescentar
perguntas conforme as respostas dadas em tempo real.

## Sequencia juridica

Com a transcricao, a identificacao, a comparacao e as perguntas fundamentadas,
a proxima fase passa a ser juridica:

1. Extrair e validar datas essenciais.
2. Calcular prescricao com memoria de calculo e campos pendentes.
3. Identificar teses defensivas sustentadas pelo processo.
4. Analisar possiveis nulidades.
5. Vincular cada nulidade a legislacao e precedentes verificaveis.

Esses blocos nao devem ser fundidos em uma unica chamada de LLM. Cada um precisa
de fontes, validacao e criterio de incerteza proprios.
