# Datas essenciais e prescricao

## Objetivo

Esta fase localiza datas e artigos que podem ser relevantes para a prescricao e
produz uma memoria de calculo por delito. A extracao e o calculo foram separados
porque encontrar uma data no PDF nao prova, sozinho, qual funcao juridica ela
exerce.

O extrator devolve candidatos com pagina, trecho, confianca da fonte e indicacao
de revisao. O defensor seleciona e confirma os dados corretos. Somente essa
versao confirmada entra no calculador.

## Escopo do primeiro calculo

O motor cobre a prescricao da pretensao punitiva pela pena maxima em abstrato,
com base nos arts. 10, 109, 111, 115, 116, 117 e 119 do Codigo Penal. Cada delito
e calculado separadamente.

O prazo-base segue a pena maxima confirmada:

| Pena maxima | Prazo-base |
| --- | --- |
| Superior a 12 anos | 20 anos |
| Superior a 8 e ate 12 anos | 16 anos |
| Superior a 4 e ate 8 anos | 12 anos |
| Superior a 2 e ate 4 anos | 8 anos |
| De 1 ate 2 anos | 4 anos |
| Inferior a 1 ano | 3 anos |

O dia inicial e incluido. Por isso, um prazo de tres anos iniciado em 10 de
janeiro de 2020 chega ao limite em 9 de janeiro de 2023. Um marco interruptivo
confirmado nessa data reinicia o prazo; um marco posterior nao recupera um prazo
ja esgotado.

## Redutor de idade

O art. 115 reduz o prazo pela metade quando o reu era menor de 21 anos na data
do fato ou maior de 70 anos na data da sentenca. O redutor e aplicado uma unica
vez, mesmo se os dois motivos estiverem presentes.

A Lei 15.160/2025 criou excecao para crimes que envolvam violencia sexual contra
a mulher. O motor aplica essa excecao apenas a fatos a partir de 4 de julho de
2025. Para fatos anteriores, a regra posterior mais gravosa nao e aplicada
retroativamente. Quando o redutor pode incidir e a natureza do delito nao foi
confirmada, o resultado fica inconclusivo e aponta o campo ausente.

## Interrupcoes e suspensoes

Os marcos interruptivos aceitos nesta versao sao recebimento da denuncia ou
queixa, pronuncia, confirmacao da pronuncia e publicacao de sentenca ou acordao
condenatorio recorrivel. Cada marco precisa ter data confirmada e pode guardar a
pagina e o trecho de origem.

Periodos fechados de suspensao prorrogam o prazo pelos dias efetivamente
suspensos. Periodos sobrepostos sao consolidados para que o mesmo dia nao seja
contado duas vezes.

Uma suspensao sem data final torna o calculo inconclusivo. No caso do art. 366
do Codigo de Processo Penal, a resposta tambem manda conferir o limite da
Sumula 415 do Superior Tribunal de Justica. O sistema nao presume uma suspensao
eterna nem inventa a data de retomada.

## Resultado

Cada delito recebe um destes estados:

`prazo_esgotado_no_calculo` significa que a data final ficou antes da data de
referencia ou de um marco interruptivo posterior.

`prazo_nao_esgotado_no_calculo` significa que o prazo final ainda nao foi
atingido dentro dos dados e do escopo informados.

`vence_na_data_referencia` destaca o dia-limite, sem fingir uma precisao de hora
que o PDF normalmente nao oferece.

`inconclusivo` apresenta exatamente os dados que faltam. Ele nao e usado como
resposta generica quando o calculo pode ser feito.

A memoria persistida inclui prazo-base, eventual redutor, todos os intervalos,
dias suspensos, marcos usados, prazo final, versao das regras e fontes juridicas.
Uma entrada identica reutiliza o mesmo identificador. Se os chunks do processo
forem substituidos, os calculos antigos sao apagados para impedir que uma memoria
continue vinculada a uma extracao superada.

## Endpoints

`GET /processo/{id}/prescricao/dados` localiza candidatos de datas, artigos e
penas, sempre marcados para revisao.

`POST /processo/{id}/prescricao/calcular` recebe os dados confirmados e salva a
memoria de calculo.

`GET /processo/{id}/prescricao/calculos/{calculo_id}` recupera a memoria
persistida.

## Limites conhecidos

O motor nao calcula prescricao retroativa, intercorrente depois da sentenca ou
da pretensao executoria. Essas modalidades dependem da pena concretamente
aplicada, publicacao da sentenca, recursos e transito em julgado, dados que ainda
nao fazem parte de um contrato estruturado confiavel.

Tambem nao classifica automaticamente crimes imprescritiveis, concursos de
crimes, leis especiais ou causas de aumento e diminuicao. A pena maxima em meses
precisa ser confirmada pelo profissional. Uma citacao a um artigo na
fundamentacao nao e transformada automaticamente em imputacao.

## Fontes juridicas

Codigo Penal compilado:
https://www.planalto.gov.br/ccivil_03/decreto-lei/del2848compilado.htm

Lei 15.160/2025:
https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/lei/l15160.htm

Codigo de Processo Penal compilado:
https://www.planalto.gov.br/ccivil_03/decreto-lei/del3689compilado.htm

Sumula 415 do Superior Tribunal de Justica:
https://arquivocidadao.stj.jus.br/index.php/sumula-415?listLimit=100&onlyDirect=1&sort=referenceCode&sortDir=asc

## Validacao tecnica

Os testes automatizados cobrem todos os limites do art. 109, o dia final do
prazo, marco no limite, marco tardio, suspensoes fechadas e sobrepostas,
suspensao aberta, delitos independentes, menoridade, idade na sentenca e a
mudanca temporal de 2025.

O extrator tambem foi executado, sem LLM, nos seis processos concluidos que ja
estavam na base local. O maior tinha 479 paginas e 736 chunks; a varredura levou
cerca de 0,64 segundo. O teste mostrou que artigos e datas repetidos precisam
ser consolidados e que candidatos de pessoas diferentes ainda exigem selecao
humana, comportamento agora refletido no contrato.
