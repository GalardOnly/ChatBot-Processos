# Benchmark de OCR em depoimentos

## Objetivo

Esta etapa mede se o texto extraido das pecas policiais e fiel o bastante para
sustentar transcricao, contradicoes e perguntas por depoente. O teste e separado
do restante do RAG: nao chama Gemini, Groq, embeddings ou ChromaDB. Assim, um
erro de OCR nao fica escondido por uma resposta bem escrita da LLM.

O benchmark usa seis paginas do processo publico `0206109-40.2024.8.06.0300`:
declaracoes, depoimentos e interrogatorio nas paginas 3, 5, 11, 13, 15 e 18.
O PDF e o texto integral nao entram no Git. O relatorio guarda apenas metricas e
as frases curtas encontradas ou ausentes.

## Gabarito

O arquivo `backend/data/ocr_benchmark_police_testimony.json` contem tres frases
curtas esperadas por pagina. A comparacao ignora maiusculas, acentos e pontuacao,
mas preserva a separacao entre palavras. Dessa forma, `voce vai morrer` nao e
considerado presente quando o OCR devolve `vocevaimorrer`.

As seis imagens foram inspecionadas visualmente durante a implementacao. Essa
revisao corrigiu quatro frases que nao correspondiam literalmente ao documento:
tres ocorrencias de `ameacando-a de morte` e a negativa do interrogatorio.

Em 03/08/2026, foi devolvida uma ficha de revisao humana confirmando que as 18
frases conferem com o texto visivel no PDF. A ficha recebida foi preservada em
`docs/revisao-humana-gabarito-ocr-aprovado.txt` e o estado passou para
`approved`. Como os campos de nome e data vieram em branco, o gabarito registra
o revisor como `nao_informado` e usa a data de recebimento. Essa lacuna de
identificacao permanece documentada e deve ser evitada nas proximas revisoes.

## Metricas e gate

Cada configuracao registra tempo, caracteres, palavras, proporcao de espacos,
tokens muito longos, paginas com palavras coladas e recall das frases esperadas.

O gate automatizado exige todos estes pontos:

1. Gabarito com revisao humana aprovada.
2. Duas familias independentes de OCR concluidas.
3. Pelo menos 90% de recall das frases curtas.
4. Nenhuma pagina classificada com palavras coladas.
5. Todas as paginas da suite processadas.

Depois do gate automatico, ainda e necessaria uma leitura humana por amostragem
para procurar nomes, numeros e negacoes inventados ou omitidos. O benchmark nao
afirma fidelidade integral apenas porque encontrou frases conhecidas.

## Resultado comparativo

O ensaio final comparou RapidOCR em CPU com EasyOCR em GPU. Todos os motores
usaram as mesmas seis paginas e o mesmo gabarito corrigido.

| Configuracao | Recall | Paginas coladas | Tempo |
| --- | ---: | ---: | ---: |
| RapidOCR zoom 1,5 | 27,8% | 6 de 6 | 44,7 s |
| RapidOCR zoom 3,0 | 33,3% | 5 de 6 | 53,0 s |
| EasyOCR em GPU | 100,0% | 0 de 6 | 60,4 s |

O RapidOCR continuou insuficiente para transcricao integral. O EasyOCR encontrou
as 18 frases verificadas, nao gerou paginas classificadas com palavras coladas e
atingiu sozinho todos os criterios de qualidade do motor principal. Com a revisao
humana aprovada e as duas familias concluidas, o gate final passou. O tempo inclui
a carga do modelo; um worker persistente ainda precisa ser medido separadamente.

Na primeira execucao, o EasyOCR obteve 77,8% porque numeros isolados do texto
vertical de autenticacao foram inseridos entre linhas do corpo. O adaptador passou
a ignorar apenas caixas detectadas nos 5% externos das margens, preservando a
ordem original do restante da pagina. A regra recebeu teste unitario e elevou o
recall para 100% sem alterar os textos esperados.

O ambiente isolado usou EasyOCR 1.7.2, PyTorch 2.11, torchvision 0.26 e CUDA. A
versao do torchvision foi alinhada com a matriz oficial de compatibilidade do
PyTorch. Esses pacotes e pesos continuam fora das dependencias de producao.

Referencias dos motores avaliados:

[EasyOCR](https://github.com/JaidedAI/EasyOCR)

[PaddleOCR](https://www.paddleocr.ai/main/en/version3.x/installation.html)

[Matriz de compatibilidade do TorchVision](https://github.com/pytorch/vision#installation)

O PaddleOCR continua como terceira opcao para uma futura ablation, mas nao e
necessario adiciona-lo antes de validar o EasyOCR em outro processo.

## Como executar

Na pasta `backend`, com o PDF disponivel apenas no ambiente local:

```powershell
python -m preparador_audiencia.ocr_benchmark_cli `
  --pdf "C:\caminho\processo.pdf" `
  --gold data/ocr_benchmark_police_testimony.json `
  --engines rapidocr:1.5 rapidocr:3.0 easyocr `
  --device gpu `
  --model-dir "C:\caminho\modelos-easyocr" `
  --output reports/benchmark-ocr-depoimentos.json
```

O comando cria JSON e Markdown em `backend/reports`, pasta ignorada pelo Git.
Nenhuma chave de API e necessaria.

Para testar EasyOCR em um ambiente com acesso a internet, a instalacao e o
primeiro download dos pesos devem ser feitos de forma consciente:

```powershell
python -m pip install easyocr
python -m preparador_audiencia.ocr_benchmark_cli `
  --pdf "C:\caminho\processo.pdf" `
  --engines rapidocr:3.0 easyocr `
  --model-dir "C:\caminho\modelos-easyocr" `
  --allow-model-download
```

Depois do primeiro download, os testes seguintes podem rodar sem
`--allow-model-download`. A escolha entre CPU e GPU deve ser medida; usar GPU nao
garante ganho quando renderizacao, transferencia de imagem e inicializacao do
modelo dominam o tempo total.

## Decisao desta etapa

O EasyOCR venceu esta comparacao e passa a ser o candidato para substituir ou
complementar o RapidOCR. O pipeline de producao ainda continua com a politica
conservadora atual: paginas com OCR colado recebem confianca baixa e nao sustentam
sozinhas transcricoes ou conclusoes.

O gate automatizado ficou bloqueado somente porque o gabarito ainda nao possui
aprovacao humana. Os proximos requisitos sao confirmar as 18 frases com uma
pessoa e repetir a avaliacao em outro processo, com outros layouts e depoimentos.
Se o ganho se mantiver, o EasyOCR pode entrar como recuperacao preferencial das
paginas escaneadas e o dossie deve ser reavaliado com os novos textos.
