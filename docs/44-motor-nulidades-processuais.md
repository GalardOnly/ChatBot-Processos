# Motor de nulidades processuais

## Objetivo

Esta fase amplia a analise de reconhecimento de pessoas com seis temas
processuais novos:

1. Cadeia de custodia.
2. Busca pessoal ou domiciliar.
3. Ausencia ou deficiencia de defesa.
4. Prova ilicita e provas derivadas.
5. Citacao, intimacao e interrogatorio.
6. Cerceamento de defesa.

Cada tema possui um catalogo JSON proprio em `backend/data/legal_rules`. Os
catalogos registram versao, data de verificacao, consultas de recuperacao,
requisitos, legislacao e precedentes oficiais.

## Funcionamento

O recuperador busca os trechos relevantes no processo com o `legal-ensemble`.
Se a busca hibrida falhar, a busca lexical assume e essa mudanca fica registrada
na resposta.

Trechos com OCR baixo ou desconhecido e trechos com padroes de prompt injection
nao sao enviados ao modelo. Quando nenhum indicio do ato processual aparece, a
LLM nao e chamada.

Gemini avalia cada requisito do catalogo. Groq continua como fallback juridico.
O modelo nao escolhe a conclusao e nao pode criar requisito ou fonte juridica.
Para marcar um requisito como observado ou nao observado, ele precisa copiar um
trecho literal e informar o identificador da fonte. O servidor confere se o
trecho existe naquela pagina e descarta citacoes inventadas.

## Conclusoes

`configurada` exige descumprimento documental e prejuizo documental, sem
contrapeso relevante. A falta total de defesa tecnica e a excecao controlada:
ela pode ser configurada sem um campo separado de prejuizo, conforme a Sumula
523 do STF.

`indicios_suficientes` indica descumprimento documentado, mas o prejuizo ainda
nao foi demonstrado ou existe prova independente, reparacao ou outro contrapeso.

`nao_configurada` exige evidencia positiva de regularidade ou prova expressa de
que o tema nao se aplica. Ausencia de informacao nao produz esse resultado.

`inconclusiva` e usada quando faltam trechos confiaveis para requisitos
essenciais.

Esses estados sao conclusoes operacionais de triagem. A resposta mostra falhas,
prejuizo, contrapesos, providencias, lacunas, trechos e paginas para permitir a
revisao do defensor.

## Persistencia e retomada

Cada tema e persistido separadamente. Uma execucao em lote que falha na quinta
chamada preserva as quatro anteriores. Repetir a chamada reutiliza os resultados
com a mesma versao de schema e catalogo, salvo quando `regenerar` for verdadeiro.

O reprocessamento dos chunks remove automaticamente todas as analises antigas,
pois suas paginas e trechos podem ter mudado.

## Endpoints

`POST /processo/{id}/analise-nulidades/{tema}` gera um tema isolado.

`GET /processo/{id}/analise-nulidades/{tema}` recupera o tema salvo.

`POST /processo/{id}/analise-nulidades` gera todos os temas ou a lista enviada
em `temas`. O lote retorna `concluido`, `parcial` ou `erro` e apresenta os erros
por tema.

`GET /processo/{id}/analise-nulidades` lista as analises persistidas.

Os identificadores aceitos sao:

`cadeia_custodia`

`busca_pessoal_domiciliar`

`ausencia_deficiencia_defesa`

`prova_ilicita_derivada`

`citacao_intimacao_interrogatorio`

`cerceamento_defesa`

O endpoint anterior de reconhecimento de pessoas permanece disponivel em
`POST /processo/{id}/analise-nulidade/reconhecimento`.

## Hugging Face

Os modelos do Hugging Face nao sao tratados como autoridade juridica. O modelo
`stjiris/bert-large-portuguese-cased-legal-mlm-sts-v1.0` foi registrado como
candidato para um benchmark futuro de recuperacao. Ele nao entrou no fluxo
padrao porque e maior que os componentes atuais e ainda nao passou por uma
ablacao equivalente contra JurisBERT e Legal-BERTimbau.

LegalBench.BR, Legal BR SFT e outros corpus juridicos podem ampliar benchmarks,
mas nao oferecem gabarito especifico com ato, descumprimento, prejuizo e pagina.
O proximo conjunto de avaliacao precisa ser proprio, separado entre treino e
teste e revisado por profissional.

## Limites

O motor analisa somente o texto extraido. Fotografias, videos, audios, lacres e
objetos visuais nao sao inspecionados diretamente.

A falta de documento entre os trechos recuperados nao prova que o ato nao
ocorreu. Por isso, informacao ausente gera `nao_localizado` e pode manter a
analise inconclusiva.

Os catalogos registram a lei e o precedente verificados em 04/08/2026. Uma
rotina de atualizacao juridica sera necessaria antes de uso em producao.

## Fontes principais

Codigo de Processo Penal:
https://www.planalto.gov.br/ccivil_03/decreto-lei/del3689compilado.htm

Constituicao Federal:
https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm

STF, Tema 280:
https://portal.stf.jus.br/jurisprudenciaRepercussao/tema.asp?num=280

STF, Sumula 523:
https://portal.stf.jus.br/jurisprudencia/sumariosumulas.asp?base=30&sumula=2729

STJ, cadeia de custodia:
https://www.stj.jus.br/sites/portalp/Paginas/Comunicacao/Noticias/2023/23042023-A-cadeia-de-custodia-no-processo-penal-do-Pacote-Anticrime-a-jurisprudencia-do-STJ.aspx
