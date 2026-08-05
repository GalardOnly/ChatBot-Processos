# Benchmark integrado de qualidade

## Objetivo

O projeto ja possui benchmarks separados para OCR, recuperacao, roteamento,
respostas e nulidade no reconhecimento. Esta fase cria uma camada comum para
acompanhar a qualidade dos motores sem misturar resultados incomparaveis.

O consolidador integrado nao executa Gemini, Groq ou modelos de embedding. Ele
recebe observacoes produzidas por uma execucao e compara essas observacoes com
um gabarito versionado. Assim, repetir o relatorio nao consome API e o custo de
uma execucao real fica explicito no numero de chamadas e tokens informado pelo
produtor das observacoes. O produtor `benchmark-chat-publico` faz chamadas
reais, mas exige limite explicito, bloqueia o split de teste por padrao e grava
respostas e fontes para reavaliacao offline.

## Arquivos

`backend/data/integrated_benchmark_v01.json` guarda o gabarito, a origem de cada
caso, o estado da revisao e os gates por motor.

`backend/data/integrated_benchmark_observations_calibration.json` e uma
calibracao sintetica do contrato. Seus resultados servem para testar o
avaliador. Eles nao foram produzidos pelos motores contra processos reais e
nao medem qualidade juridica.

`backend/src/preparador_audiencia/integrated_benchmark.py` valida os arquivos,
calcula as metricas e produz relatorios JSON e Markdown.

`backend/src/preparador_audiencia/integrated_chat_benchmark.py` produz uma
amostra real do chat sem persistir historico no banco ativo.

## Separacao entre desenvolvimento e teste

Casos de `development` podem orientar ajustes de prompts, recuperacao e regras.
Casos de `test` devem permanecer fora desse ciclo e ser usados somente para
medir uma versao candidata.

Essa separacao reduz vazamento de avaliacao, mas depende de disciplina: o
gabarito de teste nao deve ser usado para ajustar o comportamento dos motores.
Quando houver volume suficiente, o conjunto de teste pode ser mantido em um
repositorio ou armazenamento com acesso restrito.

## Revisao e gate juridico

Os estados aceitos sao `pending`, `technical_review`, `legal_approved` e
`rejected`.

Um caso so participa do gate juridico quando esta no split `test` e possui
status `legal_approved`. Casos sinteticos com revisao tecnica continuam gerando
metricas, mas o relatorio mostra `not_eligible` e nao libera o motor para piloto.

Essa regra impede que um teste criado pelos proprios desenvolvedores seja
confundido com validacao profissional.

## Metricas

O relatorio calcula, quando aplicavel:

1. Acuracia do rotulo ou conclusao esperada.
2. Precisao e recall das paginas recuperadas.
3. Hit de pagina, quando basta encontrar ao menos uma fonte valida.
4. Fidelidade das citacoes as paginas fornecidas como fonte.
5. Cobertura dos itens obrigatorios.
6. Taxa de casos com item proibido ou falso positivo.
7. Qualidade da abstencao em casos inconclusivos.
8. Taxa de erros.
9. Latencia mediana e percentil 95.
10. Chamadas de LLM, tokens e custo informado pela execucao.

O benchmark nao possui tabela de precos embutida. O custo so aparece quando o
produtor das observacoes fornece `estimated_cost_usd`, evitando que precos
desatualizados sejam tratados como verdade.

## Executar

Na pasta `backend`, a calibracao de desenvolvimento pode ser conferida sem
gravar arquivos:

```powershell
benchmark-integrado --split development --dry-run
```

Para produzir o relatorio:

```powershell
benchmark-integrado `
  --split development `
  --output reports/benchmark-integrado-calibracao.json
```

O split de teste e executado separadamente:

```powershell
benchmark-integrado `
  --split test `
  --output reports/benchmark-integrado-teste.json
```

Nenhum desses comandos chama provedores externos. Para medir uma versao real,
cada motor deve exportar suas observacoes no mesmo schema, incluindo paginas,
itens, latencia, chamadas e eventual erro.

## Suite inicial

A suite inicial possui doze casos sinteticos distribuidos entre recuperacao,
chat, transcricao, comparacao de depoimentos, perguntas para audiencia,
estrutura de sentenca, prescricao, teses defensivas, preparacao da audiencia,
nulidade no reconhecimento e nulidades processuais gerais.

Ela testa se a infraestrutura consegue pontuar capacidades diferentes e
bloquear falsos positivos. Ela nao diz se as conclusoes juridicas estao corretas
em processos reais.

## Primeira medicao publica

O relatorio real `benchmark-referencia-fts-persistente-final.json` foi convertido
para o schema integrado. Ele foi produzido pelo `legal-ensemble` com `top_k=5`
e zero chamadas de LLM sobre dez perguntas de tres acordaos publicos do STJ.

Os processos de familia e violencia domestica ficaram inteiros em
`development`, totalizando seis casos. O processo de saude suplementar ficou
inteiro em `test`, com quatro casos. Nenhum documento aparece nos dois splits.

Em desenvolvimento, o recuperador encontrou ao menos uma pagina esperada em
100% dos casos. A precisao media das paginas foi 39,7% e o recall medio de todas
as paginas esperadas foi 80,5%.

No teste, o hit tambem foi 100%, mas a precisao media foi 21,2% e o recall de
paginas foi 68,8%. Essa diferenca mostra por que hit rate isolado e insuficiente:
encontrar uma pagina correta nao significa recuperar todas as partes necessarias
para responder uma pergunta composta.

Os dez casos permanecem com revisao `pending`. Os numeros medem recuperacao
tecnica real, mas o gate continua `not_eligible` ate a revisao profissional.

## Experimentos de cobertura

Somente o split de desenvolvimento foi usado para comparar `top_k` 5, 8 e 10.
O recall de paginas foi 80,6%, 88,9% e 88,9%, respectivamente. A precisao caiu
de 39,7% para 28,5% e depois para 24,2%.

O `top_k=8` ficou registrado como candidato, mas nao virou padrao. A cobertura
adicional vem acompanhada de mais contexto irrelevante para a LLM e ainda
precisa ser medida na qualidade da resposta final.

Uma decomposicao simples de perguntas compostas tambem foi testada em
desenvolvimento. Consultas curtas como `em que data` trouxeram paginas erradas e
reduziram o recall para 66,7%. Essa abordagem foi rejeitada e nao entrou no
produto.

## Primeira medicao real do chat

Dois acordaos do conjunto de desenvolvimento foram reprocessados em banco,
armazenamento, cache OCR e Chroma isolados. Os 48 chunks resultantes ficaram com
confianca alta ou media. A primeira tentativa contra os processos antigos havia
sido corretamente bloqueada porque os chunks legados tinham confianca
`desconhecida`.

Foram executadas tres perguntas, com Gemini como principal, Groq como fallback,
`top_k=5` e limite absoluto de seis chamadas. O Gemini respondeu as tres e o
fallback nao foi usado. O hit de paginas e a fidelidade das citacoes ficaram em
100%, a cobertura conceitual ficou em 91,7% e nao houve erro. O percentil 95 de
latencia foi 65,9 segundos, acima do limite de 20 segundos definido para o chat.

O unico item ausente foi o numero do recurso na pergunta de identificacao. A
triagem passou a reconhecer esse tipo de pergunta e executar uma consulta
auxiliar apenas com numero, recurso, relator, ementa e tema. A recuperacao
offline posterior incluiu o cabecalho completo do acordao sem aumentar o
`top_k`.

O gabarito de resposta foi separado dos termos literais usados para conferir o
PDF. Alternativas declaradas, como `200m`, `200 metros` e `duzentos metros`,
contam como o mesmo conceito. O avaliador tambem recalcula esses itens a partir
da resposta salva, permitindo corrigir o gabarito sem chamar a LLM novamente.

A latencia foi decomposta depois desse resultado. Em uma medicao fria isolada,
o runtime de embeddings levou 6,945 segundos, a carga e o primeiro embedding
dos dois BERTs somaram 985 milissegundos e a primeira recuperacao levou 915
milissegundos. Com tudo aquecido, a recuperacao teve mediana de 96
milissegundos. Uma unica chamada ao Gemini levou 21,262 segundos. Portanto, na
execucao quente medida, aproximadamente 99,5% da espera ficou na geracao. O
relatorio e o criterio de medicao estao em `46-latencia-chat.md`.

## Integridade das fontes oficiais

O endpoint do STJ pode gerar bytes diferentes para o mesmo inteiro teor. Por
isso, o manifesto preserva o SHA-256 binario historico e registra tambem um
`text_sha256`, calculado sobre o texto normalizado de cada pagina. Uma mudanca
apenas nos metadados do PDF e aceita quando a impressao textual confere; qualquer
mudanca de conteudo continua bloqueada.

## Proxima validacao

O passo seguinte para latencia e medir tempo ate o primeiro token e implementar
resposta em streaming, sem retirar o ensemble que ja recupera em menos de 100
milissegundos quando aquecido. Em paralelo, a amostra de desenvolvimento deve
ser ampliada antes de liberar o processo de saude reservado ao teste. Cada gabarito
juridico deve registrar a pergunta ou tema, os fatos relevantes, as paginas, a
conclusao esperada, o motivo da abstencao quando aplicavel e a revisao do
profissional.

Os seis temas de nulidade precisam de casos positivos, negativos e
inconclusivos. Essa composicao e essencial para medir falso positivo e impedir
que o motor aprenda a sempre apontar nulidade.
