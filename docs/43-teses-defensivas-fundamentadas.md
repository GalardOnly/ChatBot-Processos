# Teses defensivas fundamentadas

## Objetivo

Esta fase transforma trechos do processo em linhas defensivas organizadas. O
resultado ajuda o defensor a enxergar rapidamente qual tese pode ser explorada,
quais paginas a sustentam, quais provas a contradizem e o que ainda precisa ser
confirmado.

## Catalogo juridico

A LLM nao pode criar uma tese juridica livremente. Ela escolhe apenas entre 13
hipoteses do catalogo versionado:

1. Inexistencia do fato.
2. Ausencia de prova da materialidade.
3. Atipicidade.
4. Autoria afastada pelas provas.
5. Insuficiencia de prova de autoria.
6. Excludente do crime ou isencao de pena.
7. Definicao juridica menos gravosa.
8. Tentativa.
9. Revisao favoravel da dosimetria.
10. Atenuante da confissao.
11. Regime inicial mais brando.
12. Substituicao por penas restritivas de direitos.
13. Prescricao.

As hipoteses absolutorias usam o art. 386 do CPP. Desclassificacao, tentativa,
dosimetria, confissao, regime, substituicao e prescricao possuem referencias
proprias do CPP ou Codigo Penal. As fontes juridicas sao carregadas do arquivo
`backend/data/legal_rules/defense_theses.json` e precisam ter dominio oficial.

## Fluxo

O recuperador consulta o processo com perguntas sobre autoria, materialidade,
depoimentos, tipificacao, pena e prescricao. A busca hibrida e usada primeiro.
Se os modelos de embedding estiverem indisponiveis, a busca lexical assume e o
resultado registra essa mudanca.

A estrutura de sentenca e adicionada como fonte quando existir. Assim, pena,
regime, dispositivo e transito podem sustentar teses de dosimetria ou extincao
da punibilidade sem depender de um resumo solto.

Gemini gera a proposta inicial. Groq e usado apenas se o modelo principal
falhar ou devolver formato invalido.

## Validacao das fontes

Cada tese precisa de ao menos um trecho literal favoravel. O servidor verifica
se o texto copiado realmente existe na fonte indicada e vincula as paginas
armazenadas. Teses sem apoio, IDs fora do catalogo e citacoes inventadas sao
descartadas.

Provas contrarias sao preservadas em campo separado. O nivel de suporte e
derivado pelo servidor:

`inicial` representa apoio em uma fonte ou pagina.

`amplo` representa apoio em mais de uma fonte ou pagina, sem prova contraria
selecionada.

`controvertido` informa que a recuperacao tambem encontrou evidencia contraria.

Esses niveis medem cobertura documental, nao a chance juridica de sucesso.

Fontes com OCR baixo ou desconhecido nao sustentam teses. Trechos com padrao de
prompt injection sao retirados antes de qualquer chamada de LLM.

## Endpoints

`POST /processo/{id}/teses-defensivas` recebe `top_k`, `max_teses` e
`regenerar`.

`GET /processo/{id}/teses-defensivas` recupera a analise persistida.

O reprocessamento dos chunks remove a estrutura de sentenca e as teses antigas.

## Limites

A analise organiza argumentos e evidencia, mas nao produz automaticamente uma
peticao ou alegacao final. A explicacao da LLM continua marcada para revisao e
deve ser confrontada com as paginas abertas pelo defensor.

Nulidades nao fazem parte deste catalogo. Elas permanecem em um modulo separado
porque exigem requisito legal, demonstracao do desrespeito, prejuizo e efeito
processual especificos.

## Fontes juridicas principais

Codigo de Processo Penal, arts. 383 e 386:
https://www.planalto.gov.br/ccivil_03/decreto-lei/del3689compilado.htm

Codigo Penal, arts. 14, 33, 44, 59, 65, 68 e 107 a 119:
https://www.planalto.gov.br/ccivil_03/decreto-lei/del2848compilado.htm
