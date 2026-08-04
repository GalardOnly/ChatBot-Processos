# Estrutura de sentenca, pena e transito em julgado

## Objetivo

Esta fase transforma sentencas, acordaos e certidoes em dados verificaveis para
as etapas juridicas seguintes. A extracao e deterministica e nao usa Gemini,
Groq ou outro modelo generativo.

O backend procura cabecalhos de sentenca e acordao, agrupa as paginas da
decisao e preserva os trechos literais que sustentam cada campo. Uma mencao a
uma sentenca em peticao, jurisprudencia ou certidao nao e tratada como nova
decisao apenas por conter essa palavra.

## Estrutura da decisao

Cada decisao pode apresentar:

1. Tipo do documento, resultado e intervalo de paginas.
2. Dispositivo literal e paginas cobertas.
3. Artigos mencionados no dispositivo.
4. Pena-base, pena intermediaria e pena definitiva.
5. Especie da pena e duracao em anos, meses e dias.
6. Dias-multa.
7. Regime inicial.
8. Deferimento ou indeferimento de substituicao da pena.
9. Deferimento ou indeferimento do sursis.
10. Confianca da extracao, avisos e necessidade de revisao.

Essa divisao acompanha a estrutura minima da sentenca prevista no art. 381 do
Codigo de Processo Penal e o metodo trifasico do art. 68 do Codigo Penal. O art.
387 do CPP exige que a sentenca condenatoria trate das circunstancias e aplique
as penas conforme as conclusoes adotadas.

## Transito em julgado

As certidoes sao estruturadas separadamente com estes escopos:

`acusacao` quando a certidao menciona Ministerio Publico ou acusacao.

`defesa` quando menciona defesa, reu ou acusado.

`ambas_partes` quando declara o encerramento para acusacao e defesa.

`indefinido` quando existe uma data, mas o texto nao permite identificar a
parte.

Nenhuma data com escopo indefinido e convertida silenciosamente em transito
para ambas as partes. A distincao sera necessaria para prescricao baseada na
pena aplicada e para a pretensao executoria. O Tema 788 do STF estabelece, para
a pretensao executoria, o transito em julgado da condenacao para ambas as
partes como termo inicial.

## Endpoints

`POST /processo/{id}/estrutura-sentenca` gera ou reutiliza a estrutura. O corpo
aceita apenas `regenerar`.

`GET /processo/{id}/estrutura-sentenca` recupera a versao persistida.

Se os chunks forem substituidos, a estrutura antiga e removida na mesma
operacao.

## Limites

Sentencas com varios reus, varios delitos ou somatorios complexos podem conter
mais de uma pena definitiva. Nesta versao, o backend devolve candidatos com
pagina e trecho, mas nao associa automaticamente cada pena a um reu e delito
quando o texto nao for inequívoco.

Uma decisao sem pena definitiva reconhecivel fica em revisao. Um processo sem
sentenca retorna `nao_localizada`; o sistema nao usa pedidos das partes ou
citacoes jurisprudenciais para inventar uma condenacao.

O modulo ainda nao calcula prescricao retroativa nem executoria. Ele fornece os
dados estruturados que faltavam para essas modalidades serem implementadas com
um contrato proprio e testes temporais.

## Fontes juridicas

Codigo de Processo Penal, arts. 381, 386 e 387:
https://www.planalto.gov.br/ccivil_03/decreto-lei/del3689compilado.htm

Codigo Penal, arts. 33, 44, 59 e 68:
https://www.planalto.gov.br/ccivil_03/decreto-lei/del2848compilado.htm

STF, Tema 788:
https://portal.stf.jus.br/jurisprudenciaRepercussao/verAndamentoProcesso.asp?classeProcesso=ARE&incidente=4661629&numeroProcesso=848107&numeroTema=788
