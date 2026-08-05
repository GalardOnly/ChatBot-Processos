from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_APPROVED_QUESTION_PATH = (
    Path(__file__).resolve().parents[2] / "data/approved_question_templates.json"
)


@dataclass(frozen=True)
class QuestionTemplate:
    id: str
    titulo: str
    area: str
    audiencia: str
    objetivo: str
    pergunta: str
    quando_usar: str
    tags: list[str]
    prioridade: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


DEFAULT_QUESTION_TEMPLATES = [
    QuestionTemplate(
        id="geral_resumo_audiencia",
        titulo="Resumo pratico para audiencia",
        area="geral",
        audiencia="qualquer",
        objetivo="Entender rapidamente o caso antes da audiencia.",
        pergunta=(
            "Prepare um resumo pratico para audiencia. Inclua partes, pedido ou acusacao, "
            "fatos centrais, pontos controvertidos e paginas de apoio."
        ),
        quando_usar="Primeira leitura do processo ou revisao rapida antes da audiencia.",
        tags=["triagem", "resumo", "audiencia"],
        prioridade=1,
    ),
    QuestionTemplate(
        id="geral_linha_tempo_explicada",
        titulo="Linha do tempo explicada",
        area="geral",
        audiencia="qualquer",
        objetivo="Ligar datas aos fatos relevantes.",
        pergunta=(
            "Monte uma linha do tempo explicada. Para cada data encontrada, diga qual fato "
            "ou ato processual ocorreu, por que importa para a audiencia e cite a pagina."
        ),
        quando_usar="Quando o processo tem muitas datas soltas ou historico confuso.",
        tags=["linha_do_tempo", "datas", "fatos"],
        prioridade=1,
    ),
    QuestionTemplate(
        id="geral_resultado_julgamento",
        titulo="Resultado do julgamento",
        area="geral",
        audiencia="qualquer",
        objetivo=(
            "Localizar decisao, provimento, orgao julgador e data do julgamento."
        ),
        pergunta=(
            "Qual foi o resultado do julgamento, qual orgao decidiu, em que data e "
            "qual providencia foi determinada? Cite as paginas."
        ),
        quando_usar="Quando a pergunta busca o desfecho de recurso, acao ou incidente.",
        tags=[
            "resultado",
            "julgamento",
            "decisao",
            "acordao",
            "provimento",
            "recurso",
            "recursos",
            "data",
            "turma",
            "orgao_julgador",
        ],
        prioridade=1,
    ),
    QuestionTemplate(
        id="geral_identificacao_julgamento",
        titulo="Identificacao do julgamento",
        area="geral",
        audiencia="qualquer",
        objetivo=(
            "Localizar tipo e numero do processo ou recurso, relator, orgao julgador "
            "e tema principal."
        ),
        pergunta=(
            "Qual e o processo ou recurso, qual o numero, quem foi o relator, qual "
            "orgao julgou e qual e o tema principal? Cite as paginas."
        ),
        quando_usar=(
            "Quando o defensor precisa identificar rapidamente o documento ou julgado."
        ),
        tags=[
            "identificacao",
            "julgamento",
            "processo",
            "recurso",
            "numero",
            "relator",
            "ementa",
            "tema",
            "orgao_julgador",
        ],
        prioridade=1,
    ),
    QuestionTemplate(
        id="saude_condicao_tratamento",
        titulo="Condicao de saude e tratamento",
        area="saude",
        audiencia="qualquer",
        objetivo=(
            "Localizar diagnostico, condicao clinica, tratamento e atendimento domiciliar."
        ),
        pergunta=(
            "Qual condicao de saude ou diagnostico aparece, qual tratamento foi indicado "
            "e onde deve ser prestado? Cite as paginas."
        ),
        quando_usar="Processos sobre saude publica, plano de saude ou home care.",
        tags=[
            "saude",
            "condicao",
            "diagnostico",
            "tratamento",
            "domiciliar",
            "home_care",
            "beneficiario",
        ],
        prioridade=1,
    ),
    QuestionTemplate(
        id="geral_provas_documentos",
        titulo="Provas e documentos essenciais",
        area="geral",
        audiencia="qualquer",
        objetivo="Separar o que o defensor precisa conferir antes da audiencia.",
        pergunta=(
            "Liste documentos, laudos, decisoes, certidoes e outras provas relevantes. "
            "Explique a utilidade pratica de cada item para audiencia e cite as paginas."
        ),
        quando_usar="Preparacao final e conferencia de documentos.",
        tags=["provas", "documentos", "checklist"],
        prioridade=1,
    ),
    QuestionTemplate(
        id="geral_contradicoes_lacunas",
        titulo="Contradicoes e lacunas",
        area="geral",
        audiencia="qualquer",
        objetivo="Achar pontos que precisam de esclarecimento.",
        pergunta=(
            "Identifique contradicoes, lacunas, pontos obscuros ou afirmacoes sem suporte "
            "claro nos trechos do processo. Diga o que precisa ser confirmado e cite paginas."
        ),
        quando_usar="Antes de montar perguntas para parte, testemunhas ou vitima.",
        tags=["contradicoes", "lacunas", "risco"],
        prioridade=1,
    ),
    QuestionTemplate(
        id="geral_perguntas_parte_assistida",
        titulo="Perguntas para a pessoa assistida",
        area="geral",
        audiencia="qualquer",
        objetivo="Preparar conversa objetiva com a pessoa assistida.",
        pergunta=(
            "Sugira perguntas que o defensor deve fazer para a pessoa assistida. Separe por "
            "tema, explique o objetivo de cada pergunta e cite paginas que motivam a pergunta."
        ),
        quando_usar="Atendimento previo ou minutos antes da audiencia.",
        tags=["perguntas", "assistido", "preparacao"],
        prioridade=1,
    ),
    QuestionTemplate(
        id="geral_riscos_urgencias",
        titulo="Riscos e urgencias",
        area="geral",
        audiencia="qualquer",
        objetivo="Apontar prazos, riscos e providencias imediatas.",
        pergunta=(
            "Identifique riscos, urgencias, prazos, determinacoes judiciais e providencias "
            "que podem impactar a audiencia. Explique a relevancia e cite paginas."
        ),
        quando_usar="Triagem do processo e revisao de ultima hora.",
        tags=["risco", "urgencia", "prazos"],
        prioridade=1,
    ),
    QuestionTemplate(
        id="criminal_tese_defensiva",
        titulo="Hipoteses defensivas",
        area="criminal",
        audiencia="instrucao",
        objetivo="Levantar caminhos de defesa com base no processo.",
        pergunta=(
            "Com base apenas no processo, quais hipoteses defensivas ou pontos favoraveis "
            "aparecem para a audiencia de instrucao? Separe fatos, provas e paginas."
        ),
        quando_usar="Preparacao de audiencia criminal de instrucao.",
        tags=["criminal", "defesa", "instrucao"],
        prioridade=2,
    ),
    QuestionTemplate(
        id="criminal_perguntas_testemunhas",
        titulo="Perguntas para testemunhas",
        area="criminal",
        audiencia="instrucao",
        objetivo="Criar roteiro de perguntas por ponto controvertido.",
        pergunta=(
            "Sugira perguntas para testemunhas a partir dos pontos controvertidos do processo. "
            "Indique o objetivo de cada pergunta e a pagina que justifica o tema."
        ),
        quando_usar="Quando houver depoimentos, boletins, laudos ou narrativas divergentes.",
        tags=["criminal", "testemunhas", "perguntas"],
        prioridade=2,
    ),
    QuestionTemplate(
        id="criminal_materialidade_autoria",
        titulo="Materialidade e autoria",
        area="criminal",
        audiencia="instrucao",
        objetivo="Separar prova do fato e prova de atribuicao.",
        pergunta=(
            "O processo traz quais elementos sobre materialidade e autoria? Aponte o que "
            "esta bem documentado, o que esta fraco ou ausente e cite paginas."
        ),
        quando_usar="Analise inicial de processo criminal.",
        tags=["criminal", "materialidade", "autoria"],
        prioridade=2,
    ),
    QuestionTemplate(
        id="criminal_reconhecimento_depoimentos",
        titulo="Reconhecimento e depoimentos",
        area="criminal",
        audiencia="instrucao",
        objetivo="Conferir confiabilidade de narrativas e reconhecimentos.",
        pergunta=(
            "Ha reconhecimentos, depoimentos ou narrativas que merecem conferencia critica? "
            "Liste pontos sensiveis, divergencias e paginas."
        ),
        quando_usar="Quando o caso depende muito de depoimentos ou reconhecimento.",
        tags=["criminal", "depoimentos", "reconhecimento"],
        prioridade=2,
    ),
    QuestionTemplate(
        id="custodia_legalidade_prisao",
        titulo="Legalidade da prisao",
        area="criminal",
        audiencia="custodia",
        objetivo="Preparar conferencia dos atos imediatos da prisao.",
        pergunta=(
            "Quais informacoes do processo ajudam a analisar a legalidade da prisao e os "
            "pontos que devem ser esclarecidos na audiencia de custodia? Cite paginas."
        ),
        quando_usar="Audiencia de custodia.",
        tags=["custodia", "prisao", "legalidade"],
        prioridade=2,
    ),
    QuestionTemplate(
        id="custodia_condicoes_pessoais",
        titulo="Condicoes pessoais",
        area="criminal",
        audiencia="custodia",
        objetivo="Organizar dados pessoais relevantes para pedido defensivo.",
        pergunta=(
            "Quais condicoes pessoais, familiares, trabalho, residencia, saude ou outros "
            "dados relevantes aparecem no processo? Cite paginas e diga o que falta confirmar."
        ),
        quando_usar="Antes de formular pedido em audiencia de custodia.",
        tags=["custodia", "condicoes_pessoais", "pedido"],
        prioridade=2,
    ),
    QuestionTemplate(
        id="custodia_violencia_policial",
        titulo="Relatos de violencia ou abuso",
        area="criminal",
        audiencia="custodia",
        objetivo="Identificar necessidade de apuracao ou cuidado imediato.",
        pergunta=(
            "O processo menciona lesoes, violencia, ameaca, abuso, falta de atendimento "
            "medico ou situacao semelhante relacionada a prisao? Cite paginas e lacunas."
        ),
        quando_usar="Audiencia de custodia ou triagem de urgencia.",
        tags=["custodia", "violencia", "saude"],
        prioridade=2,
    ),
    QuestionTemplate(
        id="violencia_domestica_fatos_medidas",
        titulo="Fatos e medidas protetivas",
        area="violencia_domestica",
        audiencia="medida_protetiva",
        objetivo="Entender fatos narrados e pedidos de protecao.",
        pergunta=(
            "Quais fatos sao narrados, quais medidas protetivas foram pedidas ou deferidas "
            "e quais pontos precisam ser confirmados em audiencia? Cite paginas."
        ),
        quando_usar="Processos de medida protetiva ou violencia domestica.",
        tags=["violencia_domestica", "medida_protetiva", "fatos"],
        prioridade=2,
    ),
    QuestionTemplate(
        id="violencia_domestica_risco",
        titulo="Indicadores de risco",
        area="violencia_domestica",
        audiencia="medida_protetiva",
        objetivo="Separar elementos de risco existentes no processo.",
        pergunta=(
            "Quais indicadores de risco, urgencia, descumprimento, ameacas ou historico de "
            "violencia aparecem no processo? Cite paginas e diga o que falta confirmar."
        ),
        quando_usar="Preparacao de audiencia com possivel risco atual.",
        tags=["violencia_domestica", "risco", "urgencia"],
        prioridade=2,
    ),
    QuestionTemplate(
        id="violencia_domestica_filhos_dependentes",
        titulo="Filhos e dependentes",
        area="violencia_domestica",
        audiencia="medida_protetiva",
        objetivo="Ver impacto familiar e necessidades de cuidado.",
        pergunta=(
            "O processo menciona filhos, dependentes, convivencia familiar, alimentos, guarda "
            "ou necessidade de protecao indireta? Cite paginas e pontos a confirmar."
        ),
        quando_usar="Quando a violencia narrada envolve contexto familiar.",
        tags=["violencia_domestica", "familia", "filhos"],
        prioridade=3,
    ),
    QuestionTemplate(
        id="familia_alimentos_necessidade_possibilidade",
        titulo="Necessidade e possibilidade",
        area="familia",
        audiencia="alimentos",
        objetivo="Mapear dados economicos essenciais.",
        pergunta=(
            "Quais elementos o processo traz sobre necessidade de quem pede alimentos e "
            "possibilidade de quem deve pagar? Cite paginas e lacunas."
        ),
        quando_usar="Audiencia de alimentos, revisao ou exoneracao.",
        tags=["familia", "alimentos", "renda"],
        prioridade=2,
    ),
    QuestionTemplate(
        id="familia_guarda_convivencia",
        titulo="Guarda e convivencia",
        area="familia",
        audiencia="guarda",
        objetivo="Organizar fatos sobre rotina, cuidado e convivencia.",
        pergunta=(
            "Quais fatos sobre guarda, convivencia, rotina de cuidado, escola, saude e rede "
            "de apoio aparecem no processo? Cite paginas e o que precisa ser confirmado."
        ),
        quando_usar="Audiencia de guarda, visitas ou regulamentacao de convivencia.",
        tags=["familia", "guarda", "convivencia"],
        prioridade=2,
    ),
    QuestionTemplate(
        id="familia_acordo_possivel",
        titulo="Pontos para acordo",
        area="familia",
        audiencia="conciliacao",
        objetivo="Achar temas negociaveis e limites do caso.",
        pergunta=(
            "Quais pontos parecem aptos a acordo e quais pontos exigem maior cautela? "
            "Indique base no processo, paginas e perguntas para confirmar."
        ),
        quando_usar="Audiencia de conciliacao em familia.",
        tags=["familia", "conciliacao", "acordo"],
        prioridade=3,
    ),
    QuestionTemplate(
        id="civel_consumidor_falha_servico",
        titulo="Falha de servico ou produto",
        area="civel",
        audiencia="conciliacao",
        objetivo="Separar fato, dano, prova e pedido.",
        pergunta=(
            "Quais fatos sustentam a alegacao de falha de servico ou produto, quais danos "
            "sao narrados, quais provas existem e quais paginas apoiam cada ponto?"
        ),
        quando_usar="Audiencia civel ou consumerista de conciliacao/instrucao.",
        tags=["civel", "consumidor", "provas"],
        prioridade=3,
    ),
    QuestionTemplate(
        id="civel_pedido_documentos",
        titulo="Pedido e documentos de suporte",
        area="civel",
        audiencia="instrucao",
        objetivo="Conferir se pedido tem documentos minimos.",
        pergunta=(
            "Qual e o pedido principal, quais documentos sustentam esse pedido e quais "
            "documentos importantes parecem ausentes? Cite paginas."
        ),
        quando_usar="Preparacao de audiencia civel de instrucao.",
        tags=["civel", "pedido", "documentos"],
        prioridade=3,
    ),
    QuestionTemplate(
        id="execucao_penal_beneficios",
        titulo="Beneficios e requisitos",
        area="execucao_penal",
        audiencia="justificacao",
        objetivo="Mapear situacao executoria e documentos relevantes.",
        pergunta=(
            "Quais informacoes aparecem sobre pena, datas, faltas, comportamento, trabalho, "
            "estudo ou requisitos para beneficio? Cite paginas e lacunas."
        ),
        quando_usar="Execucao penal e audiencia de justificacao.",
        tags=["execucao_penal", "beneficios", "datas"],
        prioridade=3,
    ),
    QuestionTemplate(
        id="execucao_penal_falta_grave",
        titulo="Falta grave",
        area="execucao_penal",
        audiencia="justificacao",
        objetivo="Preparar perguntas sobre fato disciplinar.",
        pergunta=(
            "Se houver falta disciplinar ou falta grave, quais fatos sao narrados, quais "
            "provas existem, quais contradicoes aparecem e quais paginas devem ser abertas?"
        ),
        quando_usar="Audiencia de justificacao ou incidente disciplinar.",
        tags=["execucao_penal", "falta_grave", "provas"],
        prioridade=3,
    ),
]


def list_question_templates(
    *,
    area: str | None = None,
    audiencia: str | None = None,
    tags: list[str] | None = None,
    limit: int | None = None,
    approved_path: str | Path | None = None,
) -> list[QuestionTemplate]:
    selected = DEFAULT_QUESTION_TEMPLATES + load_approved_question_templates(approved_path)
    if area:
        selected = [item for item in selected if item.area == area]
    if audiencia:
        selected = [item for item in selected if item.audiencia == audiencia]
    if tags:
        wanted = set(tags)
        selected = [item for item in selected if wanted.intersection(item.tags)]
    selected = sorted(selected, key=lambda item: (item.prioridade, item.area, item.id))
    return selected[:limit] if limit is not None else selected


def load_approved_question_templates(
    path: str | Path | None = None,
) -> list[QuestionTemplate]:
    approved_path = Path(path) if path is not None else DEFAULT_APPROVED_QUESTION_PATH
    if not approved_path.exists():
        return []
    payload = json.loads(approved_path.read_text(encoding="utf-8"))
    return [_template_from_dict(item) for item in payload.get("templates", [])]


def write_approved_question_templates(
    templates: list[QuestionTemplate],
    path: str | Path | None = None,
) -> None:
    approved_path = Path(path) if path is not None else DEFAULT_APPROVED_QUESTION_PATH
    approved_path.parent.mkdir(parents=True, exist_ok=True)
    approved_path.write_text(
        json.dumps(
            {
                "version": "0.1",
                "description": (
                    "Perguntas promovidas a partir da curadoria. Edite via fluxo de "
                    "revisao antes de usar no produto."
                ),
                "templates": [template.to_dict() for template in templates],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def question_templates_to_cases(templates: list[QuestionTemplate]) -> dict[str, object]:
    return {
        "source_id": "banco-perguntas-audiencia-v0.1",
        "document": "processo_do_usuario.pdf",
        "cases": [
            {
                "id": template.id,
                "pergunta": template.pergunta,
                "expected_pages": [],
                "expected_terms": [],
            }
            for template in templates
        ],
    }


def write_question_templates(
    templates: list[QuestionTemplate],
    output_path: str | Path,
    *,
    output_format: str,
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "json":
        path.write_text(
            json.dumps(
                [template.to_dict() for template in templates],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return
    if output_format == "cases-json":
        path.write_text(
            json.dumps(question_templates_to_cases(templates), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return
    path.write_text(render_question_templates_markdown(templates), encoding="utf-8")


def render_question_templates_markdown(templates: list[QuestionTemplate]) -> str:
    lines = [
        "# Banco de Perguntas para Audiencia",
        "",
        "Perguntas de apoio para explorar o processo pelo chat da PoC.",
        "",
    ]
    current_group = None
    for template in templates:
        group = f"{template.area} / {template.audiencia}"
        if group != current_group:
            lines.extend(["", f"## {group}", ""])
            current_group = group
        lines.extend(
            [
                f"### {template.titulo}",
                "",
                f"Objetivo: {template.objetivo}",
                "",
                f"Quando usar: {template.quando_usar}",
                "",
                f"Pergunta: {template.pergunta}",
                "",
                f"Tags: {', '.join(template.tags)}",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def _template_from_dict(item: dict[str, object]) -> QuestionTemplate:
    return QuestionTemplate(
        id=str(item["id"]),
        titulo=str(item["titulo"]),
        area=str(item["area"]),
        audiencia=str(item["audiencia"]),
        objetivo=str(item["objetivo"]),
        pergunta=str(item["pergunta"]),
        quando_usar=str(item["quando_usar"]),
        tags=[str(tag) for tag in item.get("tags", [])],
        prioridade=int(item["prioridade"]),
    )
