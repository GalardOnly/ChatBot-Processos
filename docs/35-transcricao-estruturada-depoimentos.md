# Transcricao estruturada de depoimentos

## Objetivo

Esta etapa transforma o texto ja extraido do processo em uma lista consultavel
de declaracoes, depoimentos e interrogatorios. A finalidade e permitir que o
defensor abra uma pessoa especifica, leia o texto recuperado e saiba exatamente
em quais paginas o termo aparece.

A transcricao nao usa Gemini, Groq ou outro modelo generativo. O texto retornado
e o texto armazenado nos chunks, sem resumo, correcao silenciosa ou reconstrucao
de falas. Apenas a sobreposicao tecnica criada pelo fracionamento de chunks e
removida.

## Contrato da API

`POST /processo/{processo_id}/transcricao-depoimentos` gera a transcricao. O
corpo aceita `{"regenerar": false}`. Quando ja existe um resultado valido, ele e
reutilizado. O valor `true` força uma nova leitura dos chunks atuais.

`GET /processo/{processo_id}/transcricao-depoimentos` consulta o resultado
persistido. Antes da primeira geracao, a rota devolve `404` com o codigo
`transcription_not_found`.

Cada item informa tipo do documento, titulo, pessoa, papel, fase, pagina inicial,
pagina final, texto por pagina, texto consolidado, confianca da fonte, cobertura,
avisos e necessidade de revisao.

## Regras de confiabilidade

A cobertura e `integral` somente quando o cabecalho do termo foi localizado, a
sequencia de paginas esta completa e existe um marcador formal de encerramento.
Caso contrario, o termo permanece `parcial`.

Uma transcricao exige revisao quando ocorre pelo menos uma destas situacoes:

1. A cobertura e parcial.
2. A pessoa ouvida nao pode ser identificada com seguranca.
3. A extracao apresenta palavras coladas.
4. Alguma pagina tem confianca baixa ou desconhecida.

Fontes de confianca media podem ser exibidas, mas os alertas de layout continuam
independentes. Isso evita que um OCR longo, mas mal separado, pareca confiavel.

## Persistencia e invalidacao

O resultado e salvo na tabela `structured_transcriptions` com versao de schema,
status, payload e datas. Quando os chunks de um processo sao substituidos durante
o reprocessamento, a transcricao armazenada e apagada na mesma transacao. A
proxima consulta precisa gerar um resultado novo.

## Validacao inicial

No processo publico `0206109-40.2024.8.06.0300`, o detector encontrou seis termos:

1. Declaracao nas paginas 3 e 4.
2. Declaracoes da vitima nas paginas 5 a 7.
3. Depoimento de testemunha nas paginas 11 e 12.
4. Depoimento de testemunha nas paginas 13 e 14.
5. Depoimento do condutor nas paginas 15 e 16.
6. Interrogatorio do reu nas paginas 18 e 19.

Um trecho narrativo da denuncia na pagina 54 mencionava um termo anterior. Ele
foi usado como teste de falso positivo e nao e tratado como novo depoimento.

Os seis termos atuais continuam com revisao necessaria porque foram indexados
antes da integracao do EasyOCR e apresentam palavras coladas. Isso e um alerta
correto do contrato, nao uma tentativa de corrigir o depoimento automaticamente.

## Limites conhecidos

A primeira versao reconhece termos policiais com cabecalhos identificaveis. Ela
nao transforma ata de audiencia em falas individuais quando o documento nao
possui transcricao literal. Audio, video, fotografias e depoimentos apenas
referidos por outra peca continuam fora deste contrato.
