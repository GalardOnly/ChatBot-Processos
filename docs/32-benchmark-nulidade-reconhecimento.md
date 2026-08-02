# Benchmark de nulidade no reconhecimento

## Finalidade

Este benchmark mede se o motor de nulidade chega a uma conclusao juridica
compativel com evidencias controladas. Ele separa a qualidade do raciocinio da
qualidade da recuperacao: os trechos sao entregues diretamente ao mesmo servico
usado pela API, sem ChromaDB ou ensemble de embeddings.

Os resultados esperados nao entram no prompt e nao sao usados para treinar o
modelo. Eles servem somente para comparar a resposta depois da chamada.

## Casos

A primeira suite contem seis processos sinteticos e anonimizados.

1. Fotografia isolada sem prova independente.
2. Procedimento regular com prova independente.
3. Identificacao de pessoa previamente conhecida.
4. Reconhecimento sem documentacao suficiente do rito.
5. Fotografia isolada acompanhada de prova autonoma.
6. Processo sem reconhecimento de pessoa.

Cada caso define a conclusao, o impacto processual, os resultados esperados por
requisito e as paginas que devem sustentar as afirmacoes. A suite ainda possui
status `pending` porque os rotulos precisam de revisao profissional.

## Gate

O modelo precisa atingir pelo menos 80% nas conclusoes, 80% nos requisitos e 90%
nas paginas. Nao pode haver erro de execucao nem falso positivo de forte
fundamento para invalidade.

O falso positivo e bloqueador porque pode induzir o defensor a gastar tempo com
uma tese inexistente ou tratar um procedimento regular como viciado. A nota media
nao compensa esse tipo de erro.

## Primeira rodada

O Gemini `gemini-3-flash-preview` obteve 100% nas conclusoes, impacto, requisitos
e paginas, com nota ponderada 100 e nenhum falso positivo. O tempo medio medido
por caso foi de aproximadamente 17,4 segundos. O gate foi aprovado.

O Groq `llama-3.1-8b-instant` obteve 66,7% nas conclusoes, 50% no impacto, 45,8%
nos requisitos e 71,4% nas paginas. A nota ponderada foi 58,1. Houve um falso
positivo no caso de pessoa previamente conhecida e uma resposta bloqueada pelo
limite gratuito de tokens por minuto. O gate foi reprovado.

O Groq `llama-3.3-70b-versatile` obteve 83,3% nas conclusoes e 100% nos requisitos
e paginas na rodada completa. A unica falha foi uma contradicao interna: o modelo
classificou corretamente que a pessoa nao era desconhecida, mas marcou a
aplicabilidade geral como positiva. O backend passou a derivar a aplicabilidade
do requisito estruturado, eliminando a contradicao de forma deterministica. O
caso foi repetido isoladamente e obteve 100% em conclusao, requisitos e paginas.
A suite completa nao foi repetida para preservar a cota gratuita.

## Decisao

Gemini permanece como modelo principal. O Groq 8B continua como fallback rapido
do chat geral, mas nao pode produzir conclusoes de nulidade. O fallback especifico
da analise de nulidade passa a ser o Groq 70B.

Essa decisao ainda e provisoria. O conjunto e pequeno, sintetico e escrito pela
propria equipe. Um defensor deve revisar os seis rotulos, e uma segunda suite
deve usar casos publicos ou anonimizados que nao tenham orientado a construcao do
prompt.

## Execucao

O plano sem chamadas externas pode ser conferido com:

```powershell
python -m preparador_audiencia.nullity_benchmark_cli --dry-run
```

A comparacao padrao usa Gemini e Groq, limita a rodada a 12 chamadas no pior
caso e grava JSON e Markdown na pasta local `reports`.

```powershell
python -m preparador_audiencia.nullity_benchmark_cli --delay-seconds 40
```

Um caso pode ser repetido sem consumir a suite inteira:

```powershell
python -m preparador_audiencia.nullity_benchmark_cli `
  --models groq:llama-3.3-70b-versatile `
  --case-ids identificacao-de-pessoa-conhecida `
  --max-llm-calls 1
```

O intervalo maior e necessario na cota gratuita da Groq porque o prompt juridico
controlado ocupa varios milhares de tokens. Em producao, o fallback precisara de
fila, retentativa com espera indicada pelo provedor e limite por usuario.
