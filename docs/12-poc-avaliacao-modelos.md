# PoC: Avaliacao de Modelos

## Objetivo

Continuar como PoC e testar modelos antes de escolher a pilha definitiva.

Queremos responder tres perguntas:

- como os tres embeddings juridicos trabalham juntos para recuperar os trechos certos;
- qual LLM responde melhor usando as mesmas fontes combinadas;
- qual modelo oferece melhor equilibrio entre qualidade, citacao de paginas e latencia.

## Como funciona

O arquivo de casos informa:

- pergunta;
- paginas esperadas;
- termos esperados.

O avaliador:

1. indexa os chunks separadamente em BERTikal, JurisBERT e Legal-BERTimbau;
2. executa as perguntas nos tres modelos;
3. combina os rankings por voto, score e posicao;
4. mede se as paginas esperadas apareceram no `top_k` combinado;
5. envia as mesmas fontes combinadas para cada LLM informado;
6. salva qual resposta veio de qual provedor/modelo, score, latencia e erro.

## Comando

```powershell
cd backend
avaliar-poc-modelos `
  --processo-id proc_xxxxx `
  --cases eval_cases.example.json `
  --embedding legal-ensemble `
  --llm-model gemini:gemini-3-flash-preview `
  --llm-model groq:llama-3.1-8b-instant `
  --output reports/poc-modelos.json
```

## Controle de custo

Por padrao, o avaliador limita a execucao a 4 chamadas de LLM. Isso evita
rodar uma bateria grande sem perceber.

Para ver o plano sem gastar chamadas:

```powershell
avaliar-poc-modelos `
  --processo-id proc_xxxxx `
  --cases eval_cases.example.json `
  --embedding legal-ensemble `
  --llm-model gemini:gemini-3-flash-preview `
  --llm-model groq:llama-3.1-8b-instant `
  --dry-run
```

Para liberar uma bateria maior:

```powershell
avaliar-poc-modelos ... --max-llm-calls 8
```

Se ainda passar do limite, o comando para antes de chamar qualquer API. Para
forcar conscientemente, existe `--allow-paid-over-limit`.

## Formato dos casos

```json
{
  "cases": [
    {
      "id": "audiencia",
      "pergunta": "O que o processo informa sobre audiencia?",
      "expected_pages": [3],
      "expected_terms": ["audiencia", "instrucao"]
    }
  ]
}
```

## Metricas

- `hit_rate`: porcentagem de perguntas em que alguma pagina esperada apareceu;
- `MRR`: recompensa modelos que colocam a pagina certa mais no topo;
- `score medio`: combina pagina esperada e termos esperados;
- `latencia`: tempo de resposta do LLM;
- `erro`: falha por modelo, sem derrubar a bateria toda.

## Observacao importante

A pontuacao automatica e uma triagem, nao uma sentenca final. Para o produto
juridico, a decisao deve combinar metricas com revisao humana das respostas.

## Os 3 embeddings trabalham juntos

### BERTikal

Alias: `bertikal`

Modelo: `felipemaiapolo/legalnlp-bert`

Papel no conjunto: capturar vocabulario juridico brasileiro e termos tipicos de
processo. Como e um BERT juridico geral, ele entra como voto de dominio.

### JurisBERT

Alias: `jurisbert`

Modelo: `alfaneo/jurisbert-base-portuguese-uncased`

Papel no conjunto: reforcar linguagem de jurisprudencia, decisoes e precedentes.
Ele ajuda quando o processo tem citacoes de julgados ou fundamentos judiciais.

### Legal-BERTimbau

Alias: `legal-bertimbau`

Modelo: `rufimelo/Legal-BERTimbau-sts-base`

Papel no conjunto: funcionar como recuperador semantico juridico mais equilibrado,
por ser adaptado ao dominio juridico e treinado para STS.

## Como interpretar o resultado

O `legal-ensemble` deve ser o recuperador principal da PoC. A comparacao isolada
dos tres embeddings continua util para entender qual deles esta puxando melhor
cada tipo de pergunta.

Se um deles for consistentemente ruim em PDFs reais, removemos ou reduzimos seu
peso no ensemble.

Decisao atual: Gemini e o LLM principal por qualidade de leitura. Groq fica como
fallback por velocidade e baixo tempo de resposta observado.

## Provedores de LLM aceitos

- `groq:modelo`;
- `gemini:modelo`;

Chaves de ambiente usadas na PoC atual:

- `GROQ_API_KEY`;
- `GEMINI_API_KEY`.
