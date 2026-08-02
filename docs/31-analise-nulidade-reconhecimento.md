# Analise de nulidade no reconhecimento de pessoas

## Objetivo

Este incremento transforma o feedback profissional sobre nulidades em uma
primeira analise juridica especializada. O foco inicial e o reconhecimento de
pessoas porque o tema possui requisitos verificaveis, precedentes consolidados e
impacto direto sobre autoria, prisao, recebimento da acusacao e condenacao.

A ferramenta nao se limita a avisar que pode existir uma irregularidade. Ela
entrega uma conclusao operacional para o defensor: forte fundamento para alegar
invalidade, procedimento aparentemente regular, analise inconclusiva,
reconhecimento nao localizado ou rito formal aparentemente nao aplicavel.

A conclusao acelera a triagem e a preparacao da atuacao defensiva. A declaracao
formal de nulidade e seus efeitos no caso concreto continuam dependendo da
manifestacao profissional e da decisao judicial.

## Duas fontes de informacao

O texto do processo e o catalogo juridico permanecem separados. Os trechos do
PDF informam o que aconteceu e sempre carregam pagina e confianca da extracao. O
catalogo versionado informa quais requisitos devem ser conferidos e de onde eles
vieram.

O modelo nao pode completar a lei por memoria nem obedecer a comandos existentes
dentro do PDF. Fontes processuais suspeitas de prompt injection e trechos com OCR
de baixa confianca sao retirados antes da analise.

## Fontes juridicas da primeira versao

O catalogo 2026.08.02 foi conferido em 2 de agosto de 2026 e usa apenas fontes
oficiais.

O [Codigo de Processo Penal](https://www.planalto.gov.br/ccivil_03/decreto-lei/del3689compilado.htm)
fornece os requisitos dos artigos 226 a 228.

A [Resolucao CNJ 484/2022](https://atos.cnj.jus.br/atos/detalhar/4883) orienta
um procedimento livre de apresentacao isolada, sugestao, informacao previa e
reforco da resposta.

O [Tema Repetitivo 1.258 do STJ](https://processo.stj.jus.br/repetitivos/temas_repetitivos/pesquisa.jsp?cod_tema_final=1258&cod_tema_inicial=1258&novaConsulta=true&tipo_pesquisa=T)
consolida a obrigatoriedade do procedimento, a irrepetibilidade cognitiva e o
tratamento da prova independente.

O [HC 598.886/SC](https://www.stj.jus.br/sites/portalp/SiteAssets/documentos/noticias/27102020%20HC598886-SC.pdf)
registra o precedente historico sobre reconhecimento fotografico sugestivo.

## Como a conclusao e formada

O recuperador faz varias consultas sobre descricao previa, alinhamento, termo,
separacao de reconhecedores, apresentacao sugestiva e prova independente. Gemini
recebe os trechos seguros e o catalogo controlado. Groq e usado quando o Gemini
falha ou nao devolve o contrato estruturado esperado.

Para cada requisito, o modelo so pode responder observado, nao observado, nao
localizado ou nao aplicavel. Nao observado exige evidencia processual concreta da
falha. A simples ausencia de um documento entre os trechos recuperados produz nao
localizado, nunca uma nulidade inventada.

A conclusao final nao fica inteiramente a criterio da LLM. O backend aplica uma
regra deterministica. Uma falha expressamente documentada em requisito de
validade gera forte fundamento para alegar invalidade. Todos os requisitos
aplicaveis positivamente observados permitem procedimento aparentemente regular.
Campos ausentes ou aplicabilidade duvidosa produzem resultado inconclusivo.

## Validade e impacto

A validade do reconhecimento e analisada separadamente de seu efeito no processo.
O sistema procura saber se a identificacao viciada foi determinante e se existe
prova de autoria realmente independente. Tambem registra que uma repeticao
posterior do mesmo reconhecimento nao corrige automaticamente a contaminacao do
primeiro ato.

Essa separacao evita duas falhas opostas: minimizar um reconhecimento invalido e
afirmar que toda irregularidade elimina automaticamente provas autonomas.

## Contrato da API

O endpoint `POST /processo/{id}/analise-nulidade/reconhecimento` recebe `top_k`
entre 1 e 20. A resposta traz conclusao, confianca, aplicabilidade, impacto,
requisitos, paginas processuais, fundamentos juridicos, providencias, lacunas,
modelo utilizado e versao do catalogo.

Quando a indexacao semantica ainda esta em andamento, a analise usa a busca
lexical ja disponivel. Quando Gemini e Groq falham, a API retorna 503 e nao cria
uma conclusao artificial.

## Limites atuais

Esta fase cobre somente reconhecimento de pessoas. Nulidades de busca e
apreensao, cadeia de custodia, interrogatorio, citacao, defesa tecnica e outros
temas exigirao catalogos e testes proprios.

O RAG trabalha com os trechos mais relevantes, nao com uma garantia de leitura
integral de todas as pecas. Por isso, a interface mostra as paginas e pede que o
defensor abra as evidencias antes de usar a conclusao em uma manifestacao.

O catalogo deve ser revisado quando houver mudanca legislativa, novo precedente
qualificado ou orientacao institucional. A versao usada em cada analise aparece
na resposta para permitir auditoria.
