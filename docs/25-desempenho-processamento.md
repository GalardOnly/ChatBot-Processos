# Desempenho do processamento

Esta etapa melhora a experiencia de PDFs grandes sem retirar OCR nem reduzir
a qualidade juridica do recuperador padrao.

O problema observado no PDF real de 14,9 MB tinha quatro causas combinadas. O
mesmo arquivo podia iniciar mais de um processamento, o OCR usava uma unica
sessao sem controle de recursos, os embeddings recebiam todos os trechos de
uma vez e a interface recarregava sem consultar novamente o backend.

O upload agora calcula o hash SHA-256 antes de criar um processo. Um PDF ja
concluido ou em processamento reaproveita o mesmo identificador. O backend
tambem executa somente um pipeline pesado por vez, mantendo os demais na fila.

O OCR usa resolucao 1,5x e duas sessoes independentes, cada uma com quantidade
limitada de threads. O processamento ocorre em lotes pequenos para controlar
memoria. Os embeddings de JurisBERT e Legal-BERTimbau usam lotes de 16 trechos
e os modelos ficam em cache no processo do servidor.

O status persistido passou a informar etapa, progresso atual, total,
percentual e mensagem. A interface consulta o status a cada segundo enquanto
o trabalho estiver ativo e mostra uma barra de progresso real.

No benchmark local, o PDF de 105 paginas tinha 39 paginas que exigiam OCR. A
extracao completa levou 133,4 segundos. A execucao anterior mais rapida havia
levado aproximadamente 242 segundos. A primeira vetorizacao dos 149 chunks
levou 34,2 segundos no JurisBERT e 22,8 segundos no Legal-BERTimbau. O tempo
estimado do pipeline completo ficou em aproximadamente 190 segundos. Um novo
upload do mesmo arquivo deixa de executar esse pipeline e reutiliza o
resultado concluido.

## Busca lexical persistente

A primeira implementacao da recuperacao hibrida reconstruia uma tabela FTS5 em
memoria a cada pergunta. O indice agora e persistido separadamente por processo,
com nome interno derivado por hash. Ele e criado ou substituido junto com os
chunks e a consulta do chat apenas executa a busca.

No processo de 149 chunks, a mediana isolada da busca lexical caiu de `3,658 ms`
para `1,765 ms`, reducao de `51,7%`. As 50 perguntas de regressao produziram o
mesmo ranking lexical antes e depois da mudanca. A suite multidominio manteve hit
rate de `0,90` sem triagem e `1,00` com triagem; o conjunto automatico de 50
perguntas manteve hit rate de `0,84` nas duas variantes.
