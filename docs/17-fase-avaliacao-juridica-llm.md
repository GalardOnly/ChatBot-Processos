# Fase de Avaliacao Juridica com LLM Auxiliar

Esta fase adiciona uma segunda LLM ao fluxo, nao para responder ao defensor, mas para avaliar a qualidade da resposta gerada.

O fluxo passa a ser:

1. O defensor faz uma pergunta.
2. O backend recupera fontes do processo.
3. A LLM geradora responde usando as fontes.
4. Opcionalmente, uma LLM avaliadora recebe pergunta, resposta e fontes.
5. A avaliadora retorna notas e observacoes em JSON.
6. O backend salva essa avaliacao no SQLite para formar historico de acertos e erros.

A avaliacao mede tres dimensoes principais.

Fidelidade as fontes: se a resposta esta sustentada pelos trechos recuperados e se evita inventar informacoes.

Completude juridica: se a resposta cobre os elementos minimos esperados para triagem juridica inicial.

Utilidade para audiencia: se a resposta ajuda na preparacao pratica, apontando pontos de atencao, documentos, riscos ou perguntas.

O endpoint `POST /processo/{id}/chat` continua funcionando como antes. Para ativar a avaliacao, envie:

```json
{
  "pergunta": "Quais pontos preciso confirmar em audiencia?",
  "top_k": 5,
  "avaliar": true
}
```

Tambem e possivel escolher o modelo avaliador:

```json
{
  "pergunta": "Quais pontos preciso confirmar em audiencia?",
  "top_k": 5,
  "avaliar": true,
  "avaliador_modelo": "groq:llama-3.1-8b-instant"
}
```

Por padrao, o avaliador usa `PREPARADOR_EVALUATOR_LLM`. Se essa variavel nao existir, o backend usa `groq:llama-3.1-8b-instant`.

Esta fase ainda nao cria um modelo que aprende sozinho. O caminho mais seguro e salvar as avaliacoes primeiro. Depois, quando houver volume suficiente de exemplos revisados, esse historico pode virar dataset para treinar um avaliador proprio ou ajustar prompts e recuperadores.

No estado atual, a LLM avaliadora deve ser tratada como sinal auxiliar. Ela ajuda a encontrar problemas, mas nao substitui revisao humana.

## Teste inicial de qualidade

Foi feito um teste real pequeno com o PDF `hc-312561.pdf`.

Pergunta:

```text
Qual foi o resultado do habeas corpus e qual providencia foi determinada?
```

Resposta gerada pelo Gemini:

```text
O habeas corpus nao foi conhecido, mas a ordem foi concedida de oficio. As providencias foram a expedicao da guia de recolhimento provisoria em favor da paciente e a determinacao para que o Juizo de Origem analise eventual detracao e progressao de regime.
```

A avaliacao auxiliar do Groq classificou a resposta com fidelidade `5`, completude `5`, utilidade `5` e risco de alucinacao `baixo`.

Tambem foi feito um teste negativo, com uma resposta propositalmente errada dizendo que o habeas corpus foi conhecido e a ordem foi negada. Na primeira tentativa, o avaliador foi permissivo demais e deu nota alta. O prompt foi entao endurecido para procurar contradicoes centrais, como conhecido versus nao conhecido, concedido versus negado e datas divergentes.

Depois do ajuste, o avaliador marcou a resposta errada com fidelidade `2` e risco de alucinacao `alto`. Esse resultado mostra que a camada de avaliacao e promissora, mas sensivel ao prompt e ainda precisa de testes adversariais.
