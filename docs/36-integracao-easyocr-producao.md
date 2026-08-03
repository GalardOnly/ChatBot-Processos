# Integracao do EasyOCR no processamento

## Objetivo

Esta etapa leva o motor vencedor do benchmark para o caminho real de ingestao.
Ela nao muda os endpoints: a escolha do OCR continua dentro da extracao do PDF,
antes da divisao em chunks, dos embeddings e do chat.

## Fluxo adotado

O PyMuPDF tenta extrair o texto nativo de cada pagina. Quando a pagina possui
imagem e pouco texto util, o sistema a renderiza e consulta o cache pelo hash da
imagem, versao do formato, motor, dispositivo, zoom e configuracao. Se nao houver
resultado salvo, o EasyOCR processa a pagina. Uma falha tecnica ou resposta
vazia aciona o RapidOCR somente para aquela pagina.

O leitor do EasyOCR e criado de forma tardia e permanece em memoria enquanto o
processo da API estiver ativo. Na maquina da PoC, processar as paginas
sequencialmente na GPU foi mais rapido que usar lote interno. Por isso o tamanho
padrao e um, embora a configuracao permita novos experimentos.

## Proveniencia

Cada pagina reconhecida registra o motor, a versao, o dispositivo, o uso de
cache e o uso de fallback. Esses dados seguem para os chunks, SQLite, ChromaDB,
busca lexical, busca vetorial, fontes do chat e transcricao estruturada.

Documentos indexados antes desta mudanca continuam com proveniencia ausente. A
rota `POST /processo/{id}/reprocessar` deve ser usada para gerar novamente a
extracao, os chunks e os vetores com a politica atual.

## Cache e sigilo

O cache evita repetir o trabalho caro de OCR e e escrito de forma atomica em
`backend/cache/ocr` por padrao. Ele contem o texto extraido do processo e nao e
um artefato descartavel do ponto de vista de privacidade. A exclusao definitiva
de um processo deve remover tambem suas entradas de cache quando o indice de
propriedade por processo for implementado. Ate la, o ambiente de teste precisa
restringir acesso ao diretorio e aplicar limpeza junto com os demais dados.

## Configuracao

O EasyOCR e uma dependencia opcional:

```powershell
python -m pip install -e .[dev,models,ocr-easy]
```

Configuracao recomendada para uma maquina com CUDA:

```text
PREPARADOR_OCR_ENGINE=easyocr
PREPARADOR_OCR_DEVICE=gpu
PREPARADOR_OCR_ZOOM=3.0
PREPARADOR_OCR_CACHE_DIR=cache/ocr
PREPARADOR_OCR_ALLOW_MODEL_DOWNLOAD=false
PREPARADOR_EASYOCR_MODEL_DIR=C:/caminho/modelos-easyocr
PREPARADOR_EASYOCR_BATCH_SIZE=1
```

Com `PREPARADOR_OCR_ENGINE=auto`, o sistema tambem tenta EasyOCR primeiro. Se a
dependencia ou os pesos nao estiverem disponiveis, o RapidOCR processa a pagina
e a fonte informa que houve fallback.

## Resultado verificado

No gabarito aprovado com seis paginas e 18 frases, o EasyOCR em GPU obteve 100%
de recall e nenhuma pagina com palavras coladas. Pelo gerenciador de producao,
a primeira leitura levou 40,8 segundos e a repeticao integral pelo cache levou
1,65 segundo. Nenhuma das paginas precisou do fallback.

O ganho resolve a repeticao desnecessaria, mas nao torna OCR gratuito. Um PDF
escaneado inedito ainda depende da quantidade de paginas, resolucao e GPU. A
validacao em um segundo processo com gabarito humano permanece necessaria antes
de declarar generalizacao entre tribunais e layouts.

Um segundo PDF real foi usado como teste operacional independente. Ele possui
200 paginas, das quais 22 foram selecionadas para OCR. O processamento completo,
incluindo 268 chunks e a nova indexacao juridica, levou 184,3 segundos. Trinta e
oito chunks registraram EasyOCR e nenhum precisou do fallback. Esse resultado
comprova funcionamento em outro arquivo, mas nao substitui o futuro gabarito
humano de fidelidade textual.
