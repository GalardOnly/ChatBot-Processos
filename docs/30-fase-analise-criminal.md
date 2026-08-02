# Fase de analise criminal

## Origem

Esta fase nasce do primeiro feedback profissional obtido com a POC. O defensor
identificou como trabalho repetitivo a localizacao de dados pessoais, marcos
processuais, situacao cautelar, antecedentes e depoimentos, com destaque para a
conferencia de processos possivelmente prescritos.

O objetivo inicial nao e substituir a analise juridica. A ferramenta deve reunir
os fatos e as paginas que sustentam cada dado para reduzir o tempo de conferencia.

## Entrega deste incremento

A interface passa a oferecer uma aba de analise criminal com cinco secoes.

### Identificacao e contatos

Reune nome, nascimento, filiacao, enderecos e telefones. Contatos aparecem em
ordem cronologica e o dado mais recente nao e apresentado como necessariamente
atual sem confirmacao no processo.

### Dados reunidos para prescricao

Mantem proximos os campos pedidos pelo defensor: data, horario e local do fato,
nascimento do reu, recebimento da denuncia ou queixa e suspensoes. Tambem procura
delitos, artigos, circunstancias e pena maxima quando essas informacoes estiverem
expressamente nas fontes recuperadas.

A LLM nao calcula prazo nem declara prescricao. O calculo sera um componente
deterministico posterior, com regras versionadas, fontes oficiais, casos de teste
e validacao profissional.

### Flagrante e situacao cautelar

Organiza flagrante, prisao, liberdade e medidas cautelares em ordem temporal. A
ultima noticia encontrada e identificada sem presumir que representa a situacao
atual.

### Antecedentes e processos relacionados

Lista paginas, numeros, classes, papel da pessoa e situacao mencionada. Uma
referencia a outro processo nao pode ser apresentada automaticamente como
condenacao.

### Depoimentos e provas

Mapeia os relatos por pessoa e compara convergencias e divergencias. A saida so
pode chamar uma transcricao de integral quando as fontes recuperadas cobrirem de
forma continua seu inicio e fim. Caso contrario, deve marcar a cobertura como
parcial.

Fotos, videos e prints ainda nao recebem analise visual. A POC apenas recupera o
texto extraido e as descricoes ou conclusoes escritas em laudos e peticoes.

## Decisoes de seguranca

Cada afirmacao deve citar pagina. Campos ausentes recebem a indicacao de que nao
foram localizados, sem preenchimento por conhecimento geral. As mesmas barreiras
de confianca de OCR e prompt injection aplicadas ao chat continuam valendo porque
as secoes usam o fluxo de consulta existente.

Enderecos, telefones, antecedentes e situacao prisional sao dados sensiveis. A
POC publicada por tunel deve usar apenas documentos publicos, anonimizados ou
sinteticos. Processos sigilosos dependem de autenticacao, isolamento por
organizacao, autorizacao, exclusao completa e politica de retencao.

## Proximo incremento

O motor de prescricao deve receber dados estruturados, nunca texto livre da LLM.
Antes de implementa-lo sera necessario definir regras juridicas versionadas,
fontes oficiais, tratamento de causas de reducao ou aumento, marcos interruptivos
e suspensivos, multiplos delitos e campos desconhecidos.

O criterio minimo de aceitacao sera um conjunto de casos com resultado conhecido,
revisado por profissional, cobrindo calculos simples, multiplos delitos, suspensao,
interrupcao e dados incompletos. Qualquer campo ausente deve impedir uma conclusao
categorica e produzir uma lista objetiva do que precisa ser conferido.
