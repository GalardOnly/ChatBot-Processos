# Corpo literal dos depoimentos

## Objetivo

Esta fase separa o que a pessoa efetivamente declarou das partes formais do
termo, como titulo, qualificacao, advertencias, encerramento e assinaturas. O
texto nao e resumido, corrigido nem reescrito.

## Contrato 3.0

Cada depoimento ganhou o bloco `fala`. Ele informa o status da segmentacao, a
confianca, os marcadores encontrados, as paginas inicial e final, o texto
literal consolidado e uma lista de segmentos vinculados a suas paginas.

O status `segmentada` exige um marcador de inicio e um marcador de encerramento.
Quando apenas o inicio e encontrado, o resultado fica como
`revisao_necessaria`. Sem inicio seguro, o status e `nao_localizada` e o backend
nao apresenta o documento inteiro como se fosse fala.

Transcricoes das versoes anteriores sao regeneradas localmente a partir dos
chunks quando consultadas. A atualizacao nao usa LLM.

## Regras

O inicio pode ser indicado por expressoes como `DISSE QUE`, `DECLAROU QUE`,
`RESPONDEU QUE`, `PASSOU A DECLARAR QUE` ou por um `QUE` isolado no inicio da
linha. A regra do `QUE` isolado ignora o uso de `QUE PRESTA` no titulo do termo.

O fim e delimitado por expressoes formais como `Nada mais disse`, `Nada mais
declarou` e `Nada lhe foi perguntado`. O marcador de encerramento e tudo o que
vem depois dele ficam fora da fala.

Em termos com mais de uma pagina, cada trecho mantem o numero da pagina de onde
veio. Isso permite que uma citacao posterior seja vinculada pelo servidor sem
pedir que a LLM informe a pagina.

## Seguranca e limites

A separacao e deliberadamente conservadora. Um termo com estrutura diferente
dos padroes conhecidos e encaminhado para revisao em vez de ser cortado por
aproximacao. Cabecalhos repetidos em paginas intermediarias ainda podem aparecer
no texto e precisam ser avaliados em novos layouts reais.

Atas de audiencia com dialogo entre varios falantes continuam fora deste
contrato. Elas exigem uma etapa propria de separacao por falante.
