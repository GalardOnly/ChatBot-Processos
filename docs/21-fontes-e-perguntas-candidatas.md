# Fontes e perguntas candidatas

Esta fase cria uma camada intermediaria entre pesquisa externa e banco oficial de perguntas.

O banco oficial continua pequeno e revisado. As novas perguntas entram primeiro como candidatas. Cada candidata carrega fonte, URL, tipo da fonte, area, tipo de audiencia, nota de licenca e status `candidate`.

Esse desenho evita transformar FAQ publico, manual ou dataset externo em conteudo final sem revisao. Tambem ajuda a manter rastreabilidade para um futuro colaborador entender de onde cada tema veio.

## Arquivos

- `backend/data/question_sources.json`: fontes curadas.
- `backend/src/preparador_audiencia/question_sources.py`: leitura das fontes e geracao deterministica de candidatas.
- `backend/src/preparador_audiencia/question_sources_cli.py`: comando de terminal.

## Comandos

Listar candidatas em Markdown:

```powershell
perguntas-candidatas --area criminal --audiencia custodia --official-only --limit 12
```

Exportar todas as candidatas oficiais para revisao:

```powershell
perguntas-candidatas `
  --official-only `
  --format markdown `
  --output reports/perguntas-candidatas-oficiais.md
```

Exportar candidatas para benchmark de respostas:

```powershell
perguntas-candidatas `
  --area familia `
  --format cases-json `
  --output reports/perguntas-familia-candidatas.cases.json
```

Incluir datasets de benchmark:

```powershell
perguntas-candidatas `
  --include-benchmark `
  --source-kind dataset `
  --format json `
  --output reports/perguntas-candidatas-datasets.json
```

## Regra de promocao

Uma pergunta candidata so deve entrar em `question_bank.py` depois de revisao humana ou depois de uma rodada de benchmark que mostre utilidade real.

Critérios sugeridos:

- A pergunta ajuda uma decisao pratica do defensor.
- A pergunta exige resposta baseada no processo, nao apenas conhecimento juridico generico.
- A pergunta pede citacao de pagina ou identificacao de lacuna.
- A pergunta nao induz conclusao juridica sem base.
- A fonte tem origem e uso permitidos para inspiracao.

## Objetivo de escala

A meta inicial e manter pelo menos 150 perguntas candidatas e promover aos poucos as melhores para o banco oficial.

O banco oficial nao precisa crescer rapido. Ele precisa crescer bem.
