# Roteamento Interno de Perguntas

Nesta etapa, o banco de perguntas deixou de ser tratado como uma lista de botoes
na interface e passou a funcionar como inteligencia interna do chat.

O defensor escreve a pergunta livremente, do jeito dele. Antes de buscar trechos
no processo, o backend compara essa pergunta com perguntas oficiais e perguntas
candidatas vindas da curadoria. As mais proximas viram perguntas-guia
ranqueadas.

Essas perguntas-guia nao aparecem para o usuario. Elas servem para:

1. enriquecer a consulta enviada ao recuperador vetorial;
2. ajudar o LLM a entender a intencao juridica da pergunta;
3. orientar a resposta para preparacao de audiencia;
4. manter a resposta baseada nas paginas recuperadas do processo.

O historico do chat continua salvando a pergunta original do defensor. A triagem
interna aparece apenas no prompt enviado ao LLM.

Essa decisao evita uma tela carregada de botoes e preserva a ideia central do
produto: um assistente que conversa sobre o processo e ajuda o defensor a chegar
mais rapido nos pontos relevantes para audiencia.
