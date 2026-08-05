# Amostra real para validacao juridica

## Objetivo

Esta fase cria a primeira entrada segura para processos reais autorizados. O
objetivo nao e declarar que uma substituicao automatica tornou o processo
anonimo. O objetivo e produzir um candidato auditavel, bloquear residuos e
registrar a revisao humana antes de qualquer benchmark.

O fluxo e inteiramente local. Ele nao chama Gemini, Groq, embeddings ou outra
API externa.

## Dados que permanecem fora do Git

O PDF original, o PDF candidato, a configuracao com nomes e identificadores, o
manifesto e a ficha juridica ficam em `samples/anonimizados/`. Essa pasta e
ignorada pelo Git.

Arquivos terminados em `.anonimizacao.local.json` e
`.revisao-juridica.local.json` tambem sao ignorados. O manifesto nunca grava os
valores originais; registra apenas categorias, paginas e quantidades.

## Preparar a configuracao

Use `backend/validation_sample_config.example.json` como modelo e salve uma
copia local com o sufixo `.anonimizacao.local.json`.

`authorization.confirmed` so pode ser alterado para `true` quando existir
autorizacao ou outra base interna confirmada para usar o documento na
validacao. `authorization.reference` deve ser apenas um codigo interno, sem
nome, CPF ou numero do processo.

Cada pessoa, endereco, data de nascimento ou outro valor que precise ser
substituido deve entrar em `aliases`. CPF, CNPJ, e-mail, telefone, CEP e numero
CNJ tambem possuem deteccao padrao, mas essa deteccao nao encontra nomes por
conta propria.

## Gerar o candidato

Na pasta `backend`:

```powershell
amostra-validacao preparar `
  --pdf "C:\caminho\processo-autorizado.pdf" `
  --config "C:\caminho\criminal-001.anonimizacao.local.json"
```

O comando remove os valores configurados, identificadores padronizados,
metadados pessoais, anexos, anotacoes e campos de formulario. Depois reabre o
PDF e procura residuos.

Os estados possiveis sao:

`bloqueado_residuo`: ainda existe identificador textual ou estrutura nao
sanitizada.

`revisao_visual_obrigatoria`: nao ha residuo textual detectado, mas existem
imagens que podem conter nomes, assinaturas, rostos, placas ou documentos.

`revisao_humana_pendente`: a verificacao automatica passou, mas todas as
paginas ainda precisam ser conferidas por uma pessoa.

O PDF candidato nao deve ser enviado ao defensor enquanto estiver em qualquer
um desses estados.

## Corrigir e verificar novamente

Quando uma imagem ou identificador exigir edicao manual, altere apenas o PDF
candidato com uma ferramenta de redacao que remova o conteudo, nao apenas o
cubra visualmente. Depois execute:

```powershell
amostra-validacao verificar `
  --manifest "..\samples\anonimizados\criminal-001\manifesto-anonimizacao.json" `
  --config "C:\caminho\criminal-001.anonimizacao.local.json"
```

Qualquer mudanca no PDF invalida a aprovacao anterior e gera um novo hash.

## Aprovar a anonimizacao

Depois de conferir integralmente o documento:

```powershell
amostra-validacao aprovar-anonimizacao `
  --manifest "..\samples\anonimizados\criminal-001\manifesto-anonimizacao.json" `
  --reviewer revisor-anonimizacao-01 `
  --confirm-authorization `
  --confirm-all-pages `
  --confirm-images
```

`--confirm-images` e obrigatorio quando o PDF possui imagens. A aprovacao
libera o candidato somente para o benchmark local. Ela nao autoriza publicacao,
compartilhamento aberto ou uso comercial.

## Criar a ficha juridica

```powershell
amostra-validacao criar-ficha `
  --manifest "..\samples\anonimizados\criminal-001\manifesto-anonimizacao.json"
```

A ficha traz doze perguntas sobre fatos, datas, acusacao, recebimento da
denuncia, suspensao, prisao, depoimentos, contradicoes, provas, prescricao,
teses e nulidades.

Para cada pergunta, os revisores precisam preencher `expected_pages`,
`expected_terms`, `response_relevant_pages` e `response_expected_terms`. O
campo `reviews` precisa receber duas aprovacoes independentes, usando codigos
como `defensor-01` e `defensor-02`, sem nomes pessoais.

Quando uma pergunta nao puder ser respondida a partir daquele processo, defina
`include_in_benchmark` como `false` e preencha `exclusion_reason`. A exclusao
tambem exige duas revisoes independentes. Isso evita inventar paginas ou termos
apenas para completar a ficha.

## Finalizar a suite

```powershell
amostra-validacao finalizar-ficha `
  --worksheet "..\samples\anonimizados\criminal-001\ficha-revisao-juridica.json" `
  --config "C:\caminho\criminal-001.anonimizacao.local.json"
```

O comando recusa perguntas vazias, paginas invalidas, identificadores diretos,
revisao rejeitada, revisor duplicado ou PDF alterado. Quando todos os gates
passam, ele cria `suite-referencia.json`, compativel com `suite-referencia` e
com o benchmark integrado.

A configuracao local volta a ser exigida nessa etapa para impedir que um nome
ou outro alias original seja recolocado acidentalmente na ficha.

## Limites

A deteccao automatica nao reconhece toda forma de dado pessoal. Ela nao entende
rostos, assinaturas, enderecos escritos em imagem, apelidos, relacoes familiares
ou detalhes que permitam reidentificacao por contexto.

Perguntas excluidas nao medem se o chatbot sabe responder que uma informacao nao
foi localizada. Esse comportamento precisa de uma categoria propria no
benchmark antes de ser avaliado com rigor.

Por isso, nenhum estado automatico equivale a anonimizado. A liberacao depende
de revisao visual integral e do controle de acesso ao material local.
