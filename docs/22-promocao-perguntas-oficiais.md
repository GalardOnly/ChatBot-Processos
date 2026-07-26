# Promocao de perguntas oficiais

Esta etapa fecha o ciclo entre perguntas candidatas e banco oficial.

As perguntas candidatas podem ser numerosas. O banco oficial deve continuar pequeno, revisado e adequado para aparecer ao defensor. Por isso a promocao acontece em duas fases: criar um arquivo de revisao e depois promover apenas as entradas aprovadas.

## Criar revisao

```powershell
perguntas-promocao criar-revisao `
  --area criminal `
  --audiencia custodia `
  --official-only `
  --limit 20 `
  --output reports/revisao-custodia.json
```

O arquivo gerado traz cada item com `decision: pending`. Para aprovar uma pergunta, altere para `decision: approved`. Tambem e possivel editar `approved_template` antes da promocao.

## Promover aprovadas

```powershell
perguntas-promocao promover `
  --review reports/revisao-custodia.json
```

As perguntas aprovadas entram em `data/approved_question_templates.json`. O endpoint `GET /perguntas-audiencia` e o comando `perguntas-audiencia` passam a ler esse arquivo junto com as perguntas manuais.

## Regra pratica

Promova perguntas que ajudem o defensor a fazer algo concreto:

- localizar fato relevante no processo;
- confirmar lacuna, data ou documento;
- preparar pergunta para pessoa assistida, testemunha ou parte contraria;
- revisar prova ou risco antes da audiencia;
- exigir citacao de pagina.

Evite promover perguntas que dependem apenas de conhecimento juridico generico ou que induzem uma conclusao sem base no processo.
