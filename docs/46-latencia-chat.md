# Latencia do chat

## Objetivo

Esta etapa separa a espera do chat em custos que pedem solucoes diferentes:
inicializacao do runtime de embeddings, carga dos modelos, recuperacao das
fontes e chamada ao Gemini. Medir apenas o tempo total fazia uma primeira
pergunta lenta parecer um unico problema.

O endpoint de chat agora devolve `tempos` com triagem, recuperacao, validacao de
fontes, geracao, avaliacao opcional e total. Como a recuperacao fria pode
carregar os embeddings, o comando `perfil-latencia-chat` abre esse tempo por
modelo e repete a busca com os modelos em memoria.

## Seguranca de custo

O perfilador nao chama Gemini por padrao. A chamada so acontece com
`--with-gemini --max-llm-calls 1`. Esse caminho usa somente o Gemini informado,
nao executa o Groq como fallback e nao consulta o split de teste do benchmark.

Os relatorios sao gravados em `backend/reports`, que permanece fora do Git. O
arquivo nao contem as chaves carregadas do `.env`.

## Medicao de 5 de agosto de 2026

A medicao usou o `legal-ensemble`, GPU CUDA, `top_k=5`, cinco recuperacoes e um
processo publico de desenvolvimento ja indexado. Foi feita uma unica chamada ao
`gemini:gemini-3-flash-preview`.

| Etapa | Tempo |
| --- | ---: |
| Inicializacao de PyTorch, bibliotecas e CUDA | 6.945 ms |
| Carga do JurisBERT | 430 ms |
| Primeiro embedding do JurisBERT | 206 ms |
| Carga do Legal-BERTimbau | 341 ms |
| Primeiro embedding do Legal-BERTimbau | 8 ms |
| Primeira recuperacao apos a carga | 915 ms |
| Recuperacao quente mediana | 96 ms |
| Chamada ao Gemini | 21.262 ms |
| Total frio estimado | 30.107 ms |
| Total quente estimado | 21.358 ms |

Uma medicao preliminar havia atribuido a inicializacao inteira do CUDA ao
primeiro BERT. O perfilador foi corrigido antes da medicao acima para isolar o
runtime. Isso evita concluir incorretamente que o JurisBERT, sozinho, levou todo
o tempo de partida.

## Interpretacao

O ensemble nao e o gargalo das perguntas quentes. JurisBERT e
Legal-BERTimbau, juntos, acrescentaram menos de um segundo entre carga e
primeira inferencia depois que o runtime ficou pronto. A busca quente ficou
abaixo de 100 milissegundos na mediana observada.

O Gemini respondeu por aproximadamente 99,5% do total quente. Uma unica chamada
nao forma uma distribuicao estatistica, mas e suficiente para decidir que
retirar um dos BERTs nao atacaria o atraso percebido nesta amostra.

## Decisao

O `legal-ensemble` permanece como padrao. A carga fria pode ser antecipada no
inicio do backend ou durante o processamento do primeiro documento, mas isso
remove apenas a espera da primeira pergunta depois de uma reinicializacao.

A proxima mudanca de produto deve medir tempo ate o primeiro token e entregar a
resposta do Gemini em streaming. O objetivo e reduzir a espera percebida sem
encurtar fontes ou trocar o modelo antes de comparar qualidade. Depois disso,
uma amostra maior deve medir mediana e percentil 95 da chamada generativa.
