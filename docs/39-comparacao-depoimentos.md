# Comparacao de depoimentos

## Objetivo

Esta fase compara dois depoimentos escolhidos pelo usuario. O resultado organiza
semelhancas, contradicoes potenciais e pontos que nao podem ser comparados com a
base disponivel.

## Fluxo

O backend carrega a transcricao estruturada 3.0 e exige que os dois corpos de
fala tenham inicio e fim confirmados. Gemini faz a primeira tentativa. Groq e
acionado somente se a primeira chamada falhar ou devolver um formato invalido.

A LLM recebe apenas as falas literais, separadas como conteudo nao confiavel. O
prompt proibe conclusoes sobre mentira, crime, nulidade ou efeito juridico e
esclarece que uma omissao ou diferenca de detalhe nao e automaticamente uma
contradicao.

Depois da resposta, o servidor confere cada citacao dentro dos segmentos
literais. Se um dos dois trechos nao existir, o item inteiro e descartado. As
paginas sao derivadas dos segmentos validados e nunca aceitas da LLM.

## Persistencia

Uma comparacao concluida e armazenada no SQLite e reutilizada para o mesmo par
de depoimentos. A ordem de selecao nao cria uma segunda comparacao. O parametro
`regenerar` permite refazer a analise de forma explicita.

Quando os chunks de um processo sao substituidos, suas comparacoes e sua
transcricao sao apagadas. Isso evita reutilizar conclusoes baseadas em texto
antigo. A versao da transcricao e a versao do contrato de comparacao tambem
participam da identidade do cache.

## Endpoints

`POST /processo/{id}/comparacao-depoimentos` recebe os campos
`depoimento_a_id`, `depoimento_b_id` e `regenerar`.

`GET /processo/{id}/comparacao-depoimentos/{comparacao_id}` recupera uma
comparacao persistida.

## Seguranca e limites

Textos reconhecidos pelo filtro deterministico como tentativa de prompt
injection nao sao enviados a LLM. Se Gemini e Groq falharem, a API retorna 503 e
nao grava um resultado vazio como se fosse analise concluida.

Toda divergencia recebe o estado `potencial`. A ferramenta acelera a localizacao
dos pontos que merecem conferencia, mas a classificacao juridica depende do
contexto integral do processo e da avaliacao profissional.
