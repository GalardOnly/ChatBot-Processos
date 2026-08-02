from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CriminalAnalysisSection:
    key: str
    title: str
    prompt: str
    top_k: int = 12


def _grounded_prompt(task: str) -> str:
    return (
        f"{task}\n\n"
        "Regras obrigatorias: use somente informacoes presentes nas fontes recuperadas; "
        "cite a pagina no formato [p. N] em cada afirmacao; diferencie os reus quando "
        "houver mais de um; nao complete lacunas por conhecimento geral; para qualquer "
        "campo sem apoio suficiente, escreva exatamente 'Nao localizado no processo'."
    )


CRIMINAL_ANALYSIS_SECTIONS = (
    CriminalAnalysisSection(
        key="identificacao_contatos",
        title="Identificacao e contatos",
        top_k=12,
        prompt=_grounded_prompt(
            "Organize a identificacao do reu e seus contatos. Informe nome, data de "
            "nascimento e filiacao quando constarem. Depois monte uma tabela com enderecos "
            "e telefones em ordem cronologica, contendo dado, data de referencia, contexto "
            "do documento e pagina. Destaque qual e o registro mais recente, sem afirmar "
            "que ainda e atual quando o processo nao trouxer confirmacao."
        ),
    ),
    CriminalAnalysisSection(
        key="linha_prescricao",
        title="Dados reunidos para prescricao",
        top_k=16,
        prompt=_grounded_prompt(
            "Crie um quadro compacto para conferencia de prescricao. Mantenha proximos e "
            "nesta ordem: data, horario e local do fato; data de nascimento do reu; data "
            "do recebimento da denuncia ou queixa; suspensoes do processo, com inicio, fim "
            "e motivo quando constarem. Em seguida liste separadamente cada delito imputado, "
            "artigo citado, qualificadoras ou causas mencionadas e pena maxima expressamente "
            "informada nas fontes. Registre tambem outros marcos processuais que o processo "
            "descreva como relevantes para a contagem. Nao calcule prazo, nao declare "
            "prescricao e nao busque pena fora das fontes recuperadas."
        ),
    ),
    CriminalAnalysisSection(
        key="situacao_cautelar",
        title="Flagrante e situacao cautelar",
        top_k=12,
        prompt=_grounded_prompt(
            "Informe se houve prisao em flagrante, a data e as circunstancias descritas. "
            "Monte uma linha do tempo da prisao, liberdade, revogacao ou substituicao e das "
            "medidas cautelares impostas, incluindo desde quando cada medida vigora. Termine "
            "com a noticia mais recente encontrada sobre estar preso ou solto, deixando "
            "claro quando o estado atual nao puder ser confirmado pelo processo."
        ),
    ),
    CriminalAnalysisSection(
        key="antecedentes_processos",
        title="Antecedentes e processos relacionados",
        top_k=14,
        prompt=_grounded_prompt(
            "Localize folhas de antecedentes, certidoes e referencias a outros processos. "
            "Apresente uma tabela com pagina, numero do processo, classe ou natureza, papel "
            "do reu naquele registro, como autor, reu, investigado ou testemunha, e situacao "
            "mencionada. Nao trate mera citacao como condenacao e sinalize duplicidades."
        ),
    ),
    CriminalAnalysisSection(
        key="depoimentos_provas",
        title="Depoimentos e provas",
        top_k=16,
        prompt=_grounded_prompt(
            "Mapeie os depoimentos de vitimas, testemunhas e reus no inquerito e em juizo. "
            "Para cada pessoa, indique paginas e transcreva literalmente apenas os trechos "
            "recuperados. Chame a transcricao de integral somente quando as fontes mostrarem "
            "de forma continua o inicio e o fim do depoimento; nos demais casos, marque como "
            "parcial. Depois compare convergencias e divergencias entre relatos. Liste tambem "
            "pericias, fotos, videos ou prints mencionados e as conclusoes textuais associadas. "
            "Nao interprete por conta propria o conteudo visual de imagens."
        ),
    ),
)
