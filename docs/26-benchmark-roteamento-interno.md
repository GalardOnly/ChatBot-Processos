# Benchmark do roteamento interno

## Objetivo

Este benchmark verifica se a triagem baseada no banco de perguntas juridicas ajuda a recuperar paginas mais relevantes sem substituir a forma como o defensor escreveu a pergunta.

A comparacao usa duas variantes. A primeira envia a pergunta original diretamente ao recuperador. A segunda classifica a intencao, seleciona guias somente quando a confianca e suficiente e combina os resultados da pergunta original com os resultados da pergunta enriquecida.

## Protecoes implementadas

Palavras genericas como processo, audiencia, quando, como e contexto nao contam como evidencia juridica para selecionar um guia. Um guia precisa atingir a pontuacao minima de `0,36` para participar da consulta.

Quando a pergunta possui mais de um termo relevante, uma unica coincidencia nao basta para ativar um guia. Quando nenhum guia atinge o limite, a pergunta segue sem alteracao. Quando existe uma correspondencia forte, a busca original recebe peso `1,0` e a busca enriquecida recebe peso `0,35`. Os resultados sao reunidos por fusao de ranking reciproco e o limite final de fontes continua igual ao solicitado pelo chat.

Cada consulta usa recuperacao hibrida. O `legal-ensemble` combina JurisBERT e Legal-BERTimbau para semelhanca semantica, e o indice lexical FTS5 reforca termos literais. Perguntas sobre resultado, data, numero, prazo, decisao ou valor protegem uma evidencia lexical entre os resultados sem descartar o ranking semantico.

## Casos de recuperacao

Foram geradas 50 perguntas deterministicas a partir de chunks de um processo real com 105 paginas. Cada caso usa termos juridicos presentes no texto e registra as paginas em que esses termos aparecem. Nenhuma LLM e chamada nesta etapa.

Na configuracao final desta etapa, o hit rate ficou em `0,84` com e sem triagem. O MRR passou de `0,5247` para `0,5347`: duas perguntas melhoraram, uma piorou e 47 empataram. Nenhuma LLM foi chamada.

O resultado sustenta o uso do roteamento como reforco seletivo e conservador. Ele nao sustenta substituir a pergunta original pela classificacao interna.

## Verificacao com LLM

Uma pergunta sobre datas de prisao preventiva, denuncia e citacao foi executada sobre um processo publico do STJ. A comparacao fez duas chamadas ao `gemini:gemini-3-flash-preview`, uma com a pergunta bruta e outra com a triagem.

As duas variantes recuperaram a pagina esperada, citaram essa pagina, cobriram os tres termos avaliados e obtiveram nota objetiva `1,0`. O Groq nao foi acionado.

Durante o teste, o avaliador foi corrigido para reconhecer citacoes agrupadas como `[p. 1, 7]`. Antes da correcao, apenas a primeira pagina do grupo era contabilizada.

## Como executar

Na pasta `backend`, o benchmark de recuperacao pode ser repetido sem chamadas de LLM.

```powershell
python -m preparador_audiencia.routing_benchmark_cli --processo-id ID_DO_PROCESSO --generate-cases 50 --llm-cases 0 --output reports\benchmark-roteamento.json
```

Uma amostra pequena com LLM deve ser executada somente quando houver necessidade de comparar as respostas. O comando estima o numero maximo de chamadas e bloqueia execucoes acima do limite padrao.

```powershell
python -m preparador_audiencia.routing_benchmark_cli --processo-id ID_DO_PROCESSO --cases reports\casos.json --llm-cases 1 --generator gemini:gemini-3-flash-preview --fallback groq:llama-3.1-8b-instant --output reports\benchmark-roteamento-llm.json
```

## Limites da evidencia

Os 50 casos automaticos medem recuperacao de paginas e cobertura de termos. Eles nao possuem respostas de referencia escritas por defensores e nao comprovam, sozinhos, qualidade juridica ou utilidade em audiencia.

A pergunta testada com Gemini e uma verificacao controlada pequena. Ela confirma que o fluxo tecnico funciona, mas nao permite generalizar o resultado para materias e tipos de audiencia diferentes.

O benchmark multidominio seguinte esta descrito em `docs/27-suite-referencia-multidominio.md`. Seus casos ainda precisam de revisao profissional e de respostas de referencia para medir fidelidade, completude, utilidade pratica e risco de alucinacao.
