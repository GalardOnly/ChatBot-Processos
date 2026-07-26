# Benchmark de respostas

Esta etapa mede a qualidade do fluxo completo da PoC.

O objetivo nao e apenas saber se o recuperador encontrou a pagina correta. O teste executa o caminho que o defensor usaria na pratica: o processo e indexado no recuperador escolhido, uma pergunta entra, o `legal-ensemble` recupera os trechos mais relevantes, o Gemini gera a resposta com base nas fontes e o Groq atua como avaliador auxiliar.

O avaliador da notas para tres criterios.

- Fidelidade as fontes
- Completude juridica
- Utilidade para audiencia

Ele tambem marca risco de alucinacao e registra problemas como resposta sem fonte, contradicao com o trecho recuperado, ausencia de pagina citada ou conclusao juridica alem do que o processo permite.

A partir desta fase, o relatorio tambem traz sinais objetivos calculados por regra. Esses sinais nao julgam o merito juridico, mas ajudam a calibrar a avaliacao: paginas citadas, paginas citadas fora das fontes recuperadas, proporcao de linhas afirmativas com citacao e uso de linguagem de cautela.

Na pratica, isso evita depender apenas do avaliador LLM. Se o avaliador marcar risco alto, mas os sinais objetivos mostrarem boa citacao e nenhuma pagina fora das fontes, o caso deve ser revisado manualmente antes de concluir que o gerador piorou.

## Comando

Primeiro rode em modo de planejamento para confirmar custo e configuracao.

```powershell
benchmark-respostas `
  --processo-id proc_xxxxx `
  --cases benchmark_cases.hc-312561.example.json `
  --embedding legal-ensemble `
  --top-k 5 `
  --dry-run
```

Para uma amostra pequena, limite a quantidade de perguntas.

```powershell
benchmark-respostas `
  --processo-id proc_xxxxx `
  --cases benchmark_cases.hc-312561.example.json `
  --embedding legal-ensemble `
  --limit-cases 1 `
  --max-llm-calls 3 `
  --output reports/benchmark-respostas-amostra.json
```

Para rodar de verdade, aumente o limite se a quantidade de casos exigir.

```powershell
benchmark-respostas `
  --processo-id proc_xxxxx `
  --cases benchmark_cases.hc-312561.example.json `
  --embedding legal-ensemble `
  --top-k 5 `
  --max-llm-calls 9 `
  --output reports/benchmark-respostas.json
```

O calculo de chamadas e conservador. Para cada pergunta, o comando considera uma chamada ao Gemini, uma possivel chamada ao Groq como fallback e uma chamada ao Groq como avaliador. Na pratica, quando o Gemini responde corretamente, o fallback nao e usado.

## Saidas

O comando gera dois arquivos.

- `reports/benchmark-respostas.json`: dados completos, incluindo resposta, fontes recuperadas, paginas e avaliacao.
- `reports/benchmark-respostas.md`: resumo legivel para comparar qualidade entre rodadas.

## Como interpretar

Uma rodada boa para a PoC deve ter fidelidade alta, utilidade alta e risco baixo. Completude pode variar mais, porque uma resposta conservadora pode ser fiel mas ainda faltar contexto juridico. Quando o risco de alucinacao aparece como alto, o caso deve ser lido manualmente antes de mexer em modelo, prompt ou recuperacao.

Use o campo "Risco regras" como uma segunda opiniao deterministica. Ele sobe quando a resposta cita paginas que nao vieram das fontes ou quando ha muitas linhas afirmativas sem citacao. Ele nao substitui a avaliacao LLM, mas ajuda a identificar quando o avaliador foi severo demais com uma resposta que declarou lacunas corretamente.

Esse benchmark nao substitui feedback de defensor ou promotor. Ele funciona como controle tecnico entre rodadas, para evitar que uma melhoria aparente no texto piore a confiabilidade juridica.
