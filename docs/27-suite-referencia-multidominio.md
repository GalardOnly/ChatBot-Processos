# Suite de referencia multidominio

## Objetivo

Esta etapa cria uma base pequena, reproduzivel e versionada para medir se a busca encontra paginas relevantes em materias juridicas diferentes. Ela nao treina os modelos e nao usa uma LLM para decidir o gabarito.

## Amostra

A suite usa tres acordaos publicos do STJ: REsp 1.481.531/SP, sobre convivencia familiar; HC 477.723/SP, sobre violencia domestica; e REsp 1.876.047/SP, sobre saude suplementar. O manifesto `backend/data/reference_suite_multidomain.json` registra URL oficial, hash SHA-256, dominio, perguntas, paginas e termos esperados.

Sao 3 processos, 51 paginas, 84 chunks e 10 casos. Os PDFs nao entram no Git. A ferramenta confere o hash antes de reutilizar ou processar cada arquivo.

## Fluxo

O comando `suite-referencia validar` verifica o schema sem processar documentos. O comando `suite-referencia executar --download-missing --status pending --top-k 5 --embedding legal-ensemble` baixa os PDFs ausentes, executa a ingestao real, reutiliza processos ja indexados pelo hash e produz relatorios JSON e Markdown.

Cada pergunta e executada em duas variantes. A variante bruta usa somente o texto do usuario. A variante roteada preserva a pergunta original e, quando ha confianca suficiente, acrescenta termos de um guia juridico. As duas usam recuperacao hibrida com ensemble semantico e FTS5 lexical.

## Resultado

Com `top_k=5`, a pergunta bruta obteve hit rate `0,90` e MRR `0,6450`. A triagem obteve hit rate `1,00` e MRR `0,6733`. Dois casos melhoraram, nenhum piorou e oito empataram.

Hit significa que ao menos uma das paginas esperadas apareceu entre os cinco chunks retornados. MRR mede a posicao da primeira pagina esperada. Paginas repetidas podem aparecer quando o PDF possui mais de um chunk na mesma pagina.

## Limites

Os dez casos estao em `pending`. As paginas e os termos foram conferidos tecnicamente nos PDFs, mas ainda nao foram aprovados por defensor, promotor ou outro revisor juridico.

A amostra contem acordaos, nao autos completos de primeiro grau. Ela mede recuperacao, nao fidelidade nem utilidade das respostas do Gemini ou do Groq. Os 50 casos automaticos continuam uteis para regressao, mas sao derivados do proprio processo e nao constituem avaliacao juridica independente.

## Criterio de evolucao

Uma mudanca no recuperador deve manter o hit rate multidominio, nao introduzir casos piorados e ser conferida tambem no conjunto automatico de 50 perguntas. O proximo nivel exige revisao humana dos gabaritos e respostas de referencia para avaliar completude, citacao correta, utilidade em audiencia e alucinacao.
