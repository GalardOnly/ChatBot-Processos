# Identificacao dos depoimentos

## Objetivo

Esta fase responde quatro perguntas antes de qualquer comparacao de falas: qual
termo foi encontrado, quem foi ouvido, em qual papel e qual evidencia sustenta
essa identificacao. O resultado continua deterministico e nao usa LLM para
inventar ou completar nomes.

## Contrato 2.0

Cada depoimento recebe um identificador derivado da pagina inicial e do tipo do
documento, como `dep-p0011-depoimento_testemunha`. O identificador permanece
estavel enquanto o termo continuar na mesma pagina e com a mesma classificacao.

O bloco `identificacao` informa:

1. `status`: identificado ou nao identificado.
2. `metodo`: rotulo de cabecalho, titulo nominal, qualificacao ou ausente.
3. `confianca`: alta, media ou baixa.
4. `nome_normalizado`: versao sem acentos e com espacos uniformes para permitir
   agrupamento futuro de declaracoes da mesma pessoa.
5. `trecho_evidencia`: recorte curto e literal do campo que apresentou o nome.
6. `pagina`: pagina onde a evidencia foi encontrada.

Resultados persistidos na versao 1.0 sao regenerados a partir dos chunks quando
consultados. Nenhuma chamada externa e necessaria para essa atualizacao.

## Regras conservadoras

Um rotulo explicito, como `TESTEMUNHA: NOME`, ou um titulo nominal, como
`TERMO DE DECLARACAO DE NOME`, produz confianca alta. A expressao indireta de
comparecimento em cartorio produz confianca media e deixa o item em revisao.
Quando nenhum padrao seguro existe, o nome permanece vazio e a confianca e
baixa.

A confianca mede a clareza estrutural da origem do nome. Ela nao valida a
identidade civil da pessoa e nao corrige grafia de OCR. Qualidade da extracao,
cobertura do termo e identificacao continuam sendo sinais independentes.

O detector diferencia declaracao, declaracoes da vitima, depoimento de vitima,
depoimento de testemunha, depoimento de informante, depoimento do condutor e
interrogatorio. Mencoes narrativas a um depoimento anterior nao criam um novo
item.

## Validacao

O primeiro processo real apresentou seis termos entre as paginas 3 e 19. Todos
os seis nomes foram identificados com confianca alta e os seis termos ficaram
integrais.

O segundo processo real possui outro layout e apresentou seis termos entre as
paginas 5 e 19. Depois do reprocessamento com EasyOCR, os seis nomes tambem foram
identificados por campos explicitos, com cobertura integral e sem fallback de
OCR.

Os testes automatizados cobrem nomes em linhas separadas, rotulos de vitima,
testemunha, informante, condutor e interrogado, parenteses alterados pelo OCR,
qualificacao indireta, normalizacao de acentos e rejeicao de mencao narrativa.

## Limites

Atas de audiencia sem transcricao literal ainda nao sao separadas por falante.
Uma pessoa citada apenas no corpo de outra peca nao e tratada como depoente. A
normalizacao de nomes prepara o agrupamento, mas a decisao de que duas grafias
representam a mesma pessoa ainda nao foi implementada.

A etapa seguinte recomendada e separar o corpo literal de cada fala das partes
formais do termo. Depois disso, declaracoes da mesma pessoa poderao ser alinhadas
por assunto e comparadas sem usar cabecalhos, qualificacoes ou assinaturas como
se fossem fala.
