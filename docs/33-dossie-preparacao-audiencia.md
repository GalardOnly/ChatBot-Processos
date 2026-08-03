# Dossie de preparacao da audiencia

## Origem

O primeiro feedback detalhado de um defensor mostrou que as ferramentas usadas
por ele resolvem partes diferentes do trabalho. Uma organiza datas e resume bem.
Outra identifica teses, contradicoes e nulidades. Nenhuma combina transcricao
literal dos depoimentos, datas separadas, contradicoes fundamentadas e perguntas
com objetivo no mesmo fluxo.

Esta fase inicia essa unificacao pelo backend. O Streamlit permanece fechado e
nao foi alterado, porque primeiro precisamos validar se os dados estruturados
correspondem ao processo.

## Contrato inicial

O dossie possui tres secoes persistentes.

### Marcos essenciais

Reune data, horario e local do fato, nascimento do reu, recebimento da denuncia
ou queixa, suspensoes, prisao, liberdade, audiencia e outros eventos relevantes.
Os quatro grupos pedidos para conferencia de prescricao aparecem como campos a
confirmar quando nao forem encontrados.

Na versao `0.2`, os marcos objetivos mais previsiveis usam extracao
deterministica antes da LLM. Data, horario e local do fato, nascimento,
recebimento da denuncia, flagrante, liberdade, periodo de cautelares e datas de
audiencia so entram quando um padrao esperado e um valor literal aparecem no
mesmo chunk. A LLM continua ajudando nos eventos abertos, mas nao pode
classificar o periodo de uma cautelar como suspensao do processo sem a fonte
mencionar suspensao ou o art. 366 do CPP.

Esta secao nao calcula nem declara prescricao. Ela fornece entradas verificaveis
para um futuro motor deterministico.

### Depoimentos

Organiza falas por pessoa, papel e fase processual. Um trecho so e aceito quando
coincide literalmente com o texto do chunk indicado. A cobertura fica como
parcial quando inicio, fim e continuidade nao puderem ser demonstrados.

### Contradicoes

Cada divergencia precisa de dois trechos literais confirmados. O resultado inclui
as duas fontes, a diferenca observada e sua possivel relevancia para a audiencia.
O estado e sempre `potencial`, pois a conclusao depende da leitura integral e da
avaliacao profissional.

## Persistencia e retomada

As tabelas `hearing_dossiers` e `hearing_dossier_sections` guardam o estado geral
e cada secao. Uma geracao bem-sucedida e reutilizada sem novas chamadas. Quando
uma secao falha, outra requisicao preserva os blocos concluidos e tenta novamente
apenas os incompletos. O campo `regenerar` descarta o cache quando uma nova leitura
for realmente necessaria.

O contrato possui versao propria. Uma mudanca incompativel de schema podera
forcar a reconstrucao sem misturar resultados antigos e novos.

## Validacoes de seguranca

Fontes sinalizadas pelo detector de prompt injection nao chegam ao modelo.
Chunks com confianca de OCR baixa ou desconhecida tambem ficam fora. A LLM nao
escolhe livremente a pagina devolvida: ela referencia um identificador temporario
e o backend deriva pagina, indice, tipo de documento e confianca do chunk real.

Para datas e transcricoes, indicar uma fonte valida ainda nao basta. O valor ou a
fala precisa existir literalmente no texto dessa fonte. Sugestoes que nao passam
nessa verificacao sao descartadas e registradas nos avisos da secao.

Trechos de depoimento tambem precisam ter contexto minimo. Fragmentos curtos,
palavras isoladas e passagens interrompidas deixam de ser exibidos mesmo quando
coincidem literalmente com o chunk.

## Recuperacao diversificada

Cada campo usa consultas proprias e recebe uma cota de resultados. A fusao nao
premia mais apenas o chunk que aparece em varias consultas genericas. Marcadores
processuais como `RECEBO A DENUNCIA`, `nascido aos`, termos de declaracao,
depoimentos, interrogatorio e redesignacao de audiencia sao localizados tambem
sem depender de espacos corretos no PDF.

Essa busca por marcadores complementa o ensemble semantico e o FTS5. Ela e
especialmente importante em pecas policiais digitalizadas, nas quais a camada de
texto pode juntar palavras.

## Politica de OCR para palavras coladas

Quando uma pagina possui uma camada nativa curta ou ilegivel e um OCR
substancial, o texto do OCR substitui a camada ruim em vez de ser anexado depois
dela. Se o proprio OCR continuar com muitas palavras coladas, a pagina recebe
confianca baixa e nao sustenta sozinha datas, falas ou conclusoes do dossie.

Essa decisao evita apresentar uma falsa transcricao integral. Para o processo de
validacao, os termos policiais ainda exigem um OCR melhor antes de oferecer
transcricao completa; os resumos legiveis da denuncia podem orientar a busca,
mas nao substituem a fala original.

## Endpoints

`POST /processo/{id}/dossie-audiencia` gera, retoma ou reutiliza o dossie. O corpo
aceita `top_k`, entre 8 e 30, e `regenerar`, falso por padrao.

`GET /processo/{id}/dossie-audiencia` carrega o resultado persistido sem chamar
Gemini ou Groq.

O processo precisa estar completamente indexado. Nesta primeira versao, a chamada
de geracao e sincrona, mas cada secao e salva imediatamente quando termina.
Se os dois provedores falharem em todas as secoes, o `POST` retorna `503`; o
estado de erro permanece disponivel pelo `GET` para diagnostico e nova tentativa.

## Validacao em processo real

O dossie foi executado no processo publico `0206109-40.2024.8.06.0300`, com 113
paginas e 158 chunks. A primeira execucao confirmou 21 de 21 referencias e
trechos, mas falhou em utilidade: misturou datas, omitiu o recebimento da
denuncia e trouxe falas muito curtas.

Depois da recuperacao diversificada, as fontes passaram a incluir os fatos e a
qualificacao na pagina 53, o recebimento na pagina 58, os termos policiais nas
paginas 3, 5, 11, 13, 15 e 18 e as audiencias nas paginas 93 e 107. O teste
deterministico localizou nascimento em `05/11/1995`, recebimento em `22/10/2024`,
flagrante em `02 de setembro de 2024, as 12h`, liberdade provisoria, cautelares
de `03/09/2024` a `03/09/2025` e a audiencia designada.

O resultado continua classificado como `aprovado_com_revisao`. Nao foi possivel
sustentar uma contradicao com dois trechos literais, e o RapidOCR ainda manteve
palavras coladas nos depoimentos originais. Esse resultado e honesto: a estrutura
e as referencias passaram, mas a cobertura juridica e a transcricao integral
ainda nao passaram.

## Limites desta entrega

O dossie ainda nao gera perguntas por depoente, nao calcula prescricao, nao une a
analise de nulidade ao mesmo contrato e nao interpreta visualmente fotografias ou
videos. A busca RAG tambem nao prova cobertura integral de um processo extenso.

O primeiro comparativo de OCR foi concluido. O EasyOCR recuperou todas as frases
curtas verificadas e eliminou as palavras coladas nas seis paginas policiais.
A revisao humana confirmou as 18 frases e o gate passou. Ainda e necessario
repetir a avaliacao em outro processo antes de integrar o motor a producao.
Depois dessa repeticao, o contrato do dossie pode avancar para perguntas por
depoente usando as falas recuperadas e confirmadas.

## Verificacao automatizada

```powershell
python -m pytest `
  tests/test_hearing_dossier.py `
  tests/test_hearing_dossier_facts.py `
  tests/test_hearing_dossier_repository.py `
  tests/test_api_hearing_dossier.py `
  tests/test_dossier_validation.py
```

Os testes cobrem persistencia por secao, retomada, cache, paginas inventadas,
datas ausentes da fonte, falas fabricadas, contradicoes sem dois trechos, OCR de
baixa confianca, fallback do Gemini para o Groq e os contratos da API.

Para validar um processo persistido sem abrir o Streamlit:

```powershell
validar-dossie `
  --processo-id proc_xxxxx `
  --regenerar `
  --top-k 18 `
  --output reports/validacao-dossie.json
```

O comando limita o pior caso a seis chamadas de LLM, grava JSON e Markdown e
separa falha estrutural de aprovacao com revisao.
