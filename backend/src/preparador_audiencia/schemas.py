from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

ProcessStatus = Literal["pendente", "processando", "concluido", "erro"]
SearchMode = Literal["indisponivel", "lexical", "hibrida"]
DossierStatus = Literal["pendente", "processando", "parcial", "concluido", "erro"]
DossierSectionStatus = Literal["pendente", "processando", "concluido", "erro"]
TranscriptionStatus = Literal["concluido", "revisao_necessaria", "sem_depoimentos"]


class UploadResponse(BaseModel):
    processo_id: str
    status: ProcessStatus
    reutilizado: bool = False


class ProcessStatusResponse(BaseModel):
    processo_id: str
    status: ProcessStatus
    paginas_extraidas: int
    chunks: int
    etapa: str
    progresso_atual: int
    progresso_total: int
    progresso_percentual: int
    mensagem: str | None
    erro: str | None
    reprocessamento_necessario: bool = False
    consulta_disponivel: bool = False
    modo_busca: SearchMode = "indisponivel"


class ProcessListItem(BaseModel):
    processo_id: str
    filename: str
    status: ProcessStatus
    paginas_extraidas: int
    chunks: int
    criado_em: str
    atualizado_em: str


class ProcessListResponse(BaseModel):
    processos: list[ProcessListItem]


class ReprocessResponse(BaseModel):
    processo_id: str
    status: ProcessStatus
    mensagem: str


class QuestionTemplateResponse(BaseModel):
    id: str
    titulo: str
    area: str
    audiencia: str
    objetivo: str
    pergunta: str
    quando_usar: str
    tags: list[str]
    prioridade: int


class QuestionTemplateListResponse(BaseModel):
    perguntas: list[QuestionTemplateResponse]


class SearchRequest(BaseModel):
    pergunta: str
    top_k: int = 5


class SearchSource(BaseModel):
    pagina: int
    chunk_index: int
    tipo_documento: str | None
    score: float
    trecho: str
    confianca_fonte: str = "alta"
    motor_ocr: str | None = None
    versao_ocr: str | None = None
    dispositivo_ocr: str | None = None
    cache_ocr: bool = False
    fallback_ocr: bool = False


class SearchResponse(BaseModel):
    processo_id: str
    pergunta: str
    modo_busca: SearchMode
    fontes: list[SearchSource]


class ChatRequest(BaseModel):
    pergunta: str
    top_k: int = 5
    avaliar: bool = False
    avaliador_modelo: str | None = None


class QualityEvaluationResponse(BaseModel):
    modelo_avaliador: str
    fidelidade_fontes: int
    completude_juridica: int
    utilidade_audiencia: int
    risco_alucinacao: str
    pontos_fortes: list[str]
    problemas: list[str]
    faltou: list[str]
    veredito: str
    erro: str | None


class ChatResponse(BaseModel):
    processo_id: str
    pergunta: str
    resposta: str
    modelo: str | None
    fallback_usado: bool
    modo_busca: SearchMode
    fontes: list[SearchSource]
    avaliacao: QualityEvaluationResponse | None = None


class NullityAnalysisRequest(BaseModel):
    top_k: int = 16


class NullityRequirementResponse(BaseModel):
    id: str
    categoria: str
    titulo: str
    condicao: str
    resultado: Literal[
        "observado",
        "nao_observado",
        "nao_localizado",
        "nao_aplicavel",
    ]
    justificativa: str
    paginas: list[int]
    fontes_juridicas: list[str]


class LegalSourceResponse(BaseModel):
    id: str
    titulo: str
    autoridade: str
    tipo: str
    referencia: str
    url: str


class NullityAnalysisResponse(BaseModel):
    processo_id: str
    tema: str
    titulo: str
    conclusao: Literal[
        "forte_fundamento_para_alegar_invalidade",
        "procedimento_aparentemente_regular",
        "inconclusivo",
        "reconhecimento_nao_localizado",
        "rito_formal_nao_aplicavel",
    ]
    conclusao_rotulo: str
    confianca: Literal["alta", "media", "baixa"]
    resumo: str
    aplicabilidade: str
    justificativa_aplicabilidade: str
    impacto_processual: str
    justificativa_impacto: str
    paginas_impacto: list[int]
    requisitos: list[NullityRequirementResponse]
    providencias: list[str]
    lacunas: list[str]
    modelo: str | None
    fallback_usado: bool
    modo_busca: SearchMode
    fontes_processuais: list[SearchSource]
    fontes_juridicas: list[LegalSourceResponse]
    versao_catalogo_juridico: str
    catalogo_verificado_em: str
    avisos: list[str]


class HearingDossierGenerateRequest(BaseModel):
    top_k: int = 18
    regenerar: bool = False


class DossierSourceResponse(BaseModel):
    pagina: int
    chunk_index: int
    tipo_documento: str | None = None
    confianca_fonte: str
    trecho: str


class DossierSectionBase(BaseModel):
    status: DossierSectionStatus
    modelo: str | None = None
    fallback_usado: bool = False
    recuperacao_ms: int | None = None
    geracao_ms: int | None = None
    erro: str | None = None
    atualizado_em: str
    avisos: list[str] = Field(default_factory=list)


class DossierKeyEventResponse(BaseModel):
    tipo: str
    rotulo: str
    valor: str
    pessoa: str | None = None
    descricao: str | None = None
    fontes: list[DossierSourceResponse]


class DossierMissingFieldResponse(BaseModel):
    campo: str
    rotulo: str
    motivo: str


class DossierKeyEventsSectionResponse(DossierSectionBase):
    itens: list[DossierKeyEventResponse] = Field(default_factory=list)
    campos_para_confirmar: list[DossierMissingFieldResponse] = Field(default_factory=list)


class DossierTestimonyExcerptResponse(BaseModel):
    texto: str
    fonte: DossierSourceResponse


class DossierTestimonyResponse(BaseModel):
    pessoa: str
    papel: str
    fase: str
    cobertura: Literal["parcial", "integral"]
    trechos: list[DossierTestimonyExcerptResponse]


class DossierTestimoniesSectionResponse(DossierSectionBase):
    itens: list[DossierTestimonyResponse] = Field(default_factory=list)
    lacunas: list[str] = Field(default_factory=list)


class DossierClaimResponse(BaseModel):
    texto: str
    fonte: DossierSourceResponse


class DossierContradictionResponse(BaseModel):
    titulo: str
    pessoa_a: str
    afirmacao_a: DossierClaimResponse
    pessoa_b: str
    afirmacao_b: DossierClaimResponse
    explicacao: str
    relevancia_audiencia: str
    estado: Literal["potencial"]


class DossierContradictionsSectionResponse(DossierSectionBase):
    itens: list[DossierContradictionResponse] = Field(default_factory=list)
    lacunas: list[str] = Field(default_factory=list)


class HearingDossierResponse(BaseModel):
    processo_id: str
    status: DossierStatus
    versao: str
    erro: str | None = None
    criado_em: str
    atualizado_em: str
    marcos_essenciais: DossierKeyEventsSectionResponse
    depoimentos: DossierTestimoniesSectionResponse
    contradicoes: DossierContradictionsSectionResponse


class StructuredTranscriptionGenerateRequest(BaseModel):
    regenerar: bool = False


class TranscriptionPageResponse(BaseModel):
    pagina: int
    texto: str
    confianca_fonte: str
    palavras_coladas: bool
    motor_ocr: str | None = None
    versao_ocr: str | None = None
    dispositivo_ocr: str | None = None
    cache_ocr: bool = False
    fallback_ocr: bool = False


class TestimonyIdentificationResponse(BaseModel):
    status: Literal["identificado", "nao_identificado"]
    metodo: Literal[
        "rotulo_cabecalho",
        "titulo_nominal",
        "qualificacao",
        "nao_identificado",
    ]
    confianca: Literal["alta", "media", "baixa"]
    nome_normalizado: str | None
    trecho_evidencia: str | None
    pagina: int | None


class TestimonyBodySegmentResponse(BaseModel):
    pagina: int
    texto: str


class TestimonyBodyResponse(BaseModel):
    status: Literal["segmentada", "revisao_necessaria", "nao_localizada"]
    confianca: Literal["alta", "media", "baixa"]
    marcador_inicio: str | None
    marcador_fim: str | None
    pagina_inicial: int | None
    pagina_final: int | None
    segmentos: list[TestimonyBodySegmentResponse] = Field(default_factory=list)
    texto_literal: str
    avisos: list[str] = Field(default_factory=list)


class StructuredTestimonyResponse(BaseModel):
    id_depoimento: str
    ordem: int
    tipo_documento: str
    titulo: str
    pessoa: str | None
    papel: Literal[
        "vitima",
        "testemunha",
        "condutor",
        "reu",
        "declarante",
        "informante",
        "outro",
    ]
    identificacao: TestimonyIdentificationResponse
    fase: Literal["inquerito", "juizo", "outro"]
    cobertura: Literal["integral", "parcial"]
    fala: TestimonyBodyResponse
    pagina_inicial: int
    pagina_final: int
    paginas: list[TranscriptionPageResponse]
    texto_consolidado: str
    confianca_fonte: str
    revisao_necessaria: bool
    avisos: list[str] = Field(default_factory=list)


class StructuredTranscriptionResponse(BaseModel):
    processo_id: str
    status: TranscriptionStatus
    versao: str
    depoimentos: list[StructuredTestimonyResponse] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)
    gerado_em: str
    atualizado_em: str


class TestimonyComparisonRequest(BaseModel):
    depoimento_a_id: str
    depoimento_b_id: str
    regenerar: bool = False


class TestimonyComparisonReferenceResponse(BaseModel):
    id_depoimento: str
    pessoa: str | None
    papel: str
    fase: str
    pagina_inicial: int
    pagina_final: int


class TestimonyComparisonExcerptResponse(BaseModel):
    texto: str
    paginas: list[int]


class TestimonyComparisonItemResponse(BaseModel):
    tema: str
    fala_a: TestimonyComparisonExcerptResponse
    fala_b: TestimonyComparisonExcerptResponse
    explicacao: str
    estado: Literal["coincidente", "potencial"]


class TestimonyComparisonResponse(BaseModel):
    comparacao_id: str
    processo_id: str
    versao: str
    versao_transcricao: str
    modelo: str
    fallback_usado: bool
    depoimento_a: TestimonyComparisonReferenceResponse
    depoimento_b: TestimonyComparisonReferenceResponse
    semelhancas: list[TestimonyComparisonItemResponse] = Field(default_factory=list)
    contradicoes_potenciais: list[TestimonyComparisonItemResponse] = Field(
        default_factory=list
    )
    pontos_nao_comparaveis: list[str] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)
    gerado_em: str
    atualizado_em: str


class TestimonyQuestionGuideRequest(BaseModel):
    max_perguntas: int = 8
    regenerar: bool = False


class TestimonyQuestionSupportResponse(BaseModel):
    depoimento_id: str
    pessoa: str | None
    papel: str
    texto: str
    paginas: list[int]
    origem: str


class TestimonyQuestionResponse(BaseModel):
    ordem: int
    tema: str
    pergunta: str
    objetivo: str
    tipo: Literal[
        "esclarecimento",
        "cronologia",
        "percepcao",
        "contradicao_potencial",
        "confirmacao",
    ]
    prioridade: int
    apoios: list[TestimonyQuestionSupportResponse] = Field(default_factory=list)


class TestimonyQuestionGuideResponse(BaseModel):
    roteiro_id: str
    processo_id: str
    versao: str
    versao_transcricao: str
    modelo: str
    fallback_usado: bool
    depoimento: TestimonyComparisonReferenceResponse
    perguntas: list[TestimonyQuestionResponse] = Field(default_factory=list)
    pontos_para_confirmar: list[str] = Field(default_factory=list)
    comparacoes_utilizadas: list[str] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)
    gerado_em: str
    atualizado_em: str


class PrescriptionDateCandidateResponse(BaseModel):
    id: str
    tipo_evento: str
    rotulo: str
    natureza: str
    data: date
    valor_original: str
    pagina: int
    chunk_index: int
    trecho: str
    confianca_fonte: str
    confianca_candidato: Literal["alta", "media", "baixa"]
    revisao_necessaria: bool


class PrescriptionOffenseCandidateResponse(BaseModel):
    id: str
    artigo: str
    pena_maxima_meses: int | None
    pagina: int
    chunk_index: int
    trecho: str
    confianca_fonte: str
    revisao_necessaria: bool


class PrescriptionDataResponse(BaseModel):
    processo_id: str
    versao: str
    datas: list[PrescriptionDateCandidateResponse] = Field(default_factory=list)
    delitos: list[PrescriptionOffenseCandidateResponse] = Field(default_factory=list)
    campos_ausentes: list[str] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)


PrescriptionInterruptiveType = Literal[
    "recebimento_denuncia",
    "recebimento_queixa",
    "pronuncia",
    "confirmacao_pronuncia",
    "sentenca_condenatoria_recorrivel",
    "acordao_condenatorio_recorrivel",
]


class PrescriptionInterruptiveMilestoneRequest(BaseModel):
    tipo: PrescriptionInterruptiveType
    data: date
    pagina: int | None = Field(default=None, ge=1)
    trecho: str | None = None


class PrescriptionSuspensionPeriodRequest(BaseModel):
    tipo: Literal["art_116", "cpp_366", "cpp_368", "outra_legal"]
    inicio: date
    fim: date | None = None
    pagina: int | None = Field(default=None, ge=1)
    trecho: str | None = None


class PrescriptionOffenseRequest(BaseModel):
    id: str = Field(min_length=1)
    descricao: str = Field(min_length=1)
    artigo: str = Field(min_length=1)
    pena_maxima_meses: int = Field(gt=0)
    tipo_termo_inicial: Literal[
        "consumacao",
        "fim_tentativa",
        "fim_permanencia",
        "conhecimento_fato",
        "vitima_18_anos",
    ]
    data_termo_inicial: date
    data_fato: date
    violencia_sexual_contra_mulher: bool | None = None
    marcos_interruptivos: list[PrescriptionInterruptiveMilestoneRequest] = Field(
        default_factory=list
    )
    periodos_suspensao: list[PrescriptionSuspensionPeriodRequest] = Field(
        default_factory=list
    )


class PrescriptionCalculationRequest(BaseModel):
    data_referencia: date
    reu: str | None = None
    data_nascimento_reu: date | None = None
    situacao_sentenca: Literal["nao_proferida", "proferida", "desconhecida"]
    data_sentenca_condenatoria: date | None = None
    delitos: list[PrescriptionOffenseRequest] = Field(min_length=1)


class PrescriptionIntervalResponse(BaseModel):
    inicio: date
    prazo_final: date
    fim_avaliado: date
    motivo_fim: str
    status: str
    dias_suspensos: int


class PrescriptionOffenseResultResponse(BaseModel):
    id: str
    descricao: str
    artigo: str
    status: Literal[
        "prazo_esgotado_no_calculo",
        "prazo_nao_esgotado_no_calculo",
        "vence_na_data_referencia",
        "inconclusivo",
    ]
    prazo_base_meses: int
    prazo_aplicado_meses: int | None
    redutor_art_115_aplicado: bool
    motivos_redutor_art_115: list[str] = Field(default_factory=list)
    prazo_final: date | None
    dias_ate_prazo: int | None
    intervalos: list[PrescriptionIntervalResponse] = Field(default_factory=list)
    campos_ausentes: list[str] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)


class PrescriptionLegalSourceResponse(BaseModel):
    id: str
    titulo: str
    url: str


class PrescriptionCalculationResponse(BaseModel):
    calculo_id: str
    processo_id: str
    status: Literal[
        "inconclusivo",
        "ha_prazo_esgotado_no_calculo",
        "ha_prazo_no_limite",
        "prazos_nao_esgotados_no_calculo",
    ]
    data_referencia: date
    versao_calculo: str
    versao_regras_juridicas: str
    delitos: list[PrescriptionOffenseResultResponse]
    fontes_juridicas: list[PrescriptionLegalSourceResponse]
    avisos: list[str]
    gerado_em: str
    atualizado_em: str


class JudgmentStructureGenerateRequest(BaseModel):
    regenerar: bool = False


class JudgmentDispositionResponse(BaseModel):
    texto: str
    paginas: list[int]


class JudgmentArticleResponse(BaseModel):
    artigo: str
    pagina: int
    trecho: str


class AppliedPenaltyResponse(BaseModel):
    fase: Literal["base", "intermediaria", "definitiva", "nao_identificada"]
    especie: Literal["reclusao", "detencao", "prisao_simples"]
    anos: int
    meses: int
    dias: int
    pagina: int
    trecho: str


class JudgmentFineResponse(BaseModel):
    dias_multa: int
    pagina: int
    trecho: str


class JudgmentRegimeResponse(BaseModel):
    valor: Literal["fechado", "semiaberto", "aberto"]
    pagina: int
    trecho: str


class JudgmentBinaryDecisionResponse(BaseModel):
    resultado: Literal["deferida", "indeferida", "nao_localizada"]
    pagina: int | None
    trecho: str | None


class JudgmentDecisionResponse(BaseModel):
    id_decisao: str
    tipo_documento: Literal["sentenca", "acordao"]
    resultado: Literal["condenatoria", "absolutoria", "mista", "nao_identificado"]
    pagina_inicial: int
    pagina_final: int
    dispositivo: JudgmentDispositionResponse | None
    artigos_aplicados: list[JudgmentArticleResponse] = Field(default_factory=list)
    penas_aplicadas: list[AppliedPenaltyResponse] = Field(default_factory=list)
    multa: JudgmentFineResponse | None
    regime_inicial: JudgmentRegimeResponse | None
    substituicao_pena: JudgmentBinaryDecisionResponse
    sursis: JudgmentBinaryDecisionResponse
    confianca_fonte: str
    revisao_necessaria: bool
    avisos: list[str] = Field(default_factory=list)


class FinalJudgmentResponse(BaseModel):
    id_transito: str
    escopo: Literal["acusacao", "defesa", "ambas_partes", "indefinido"]
    data: date
    pagina: int
    trecho: str
    confianca_fonte: str
    revisao_necessaria: bool


class JudgmentStructureResponse(BaseModel):
    processo_id: str
    status: Literal["concluido", "revisao_necessaria", "nao_localizada"]
    versao: str
    decisoes: list[JudgmentDecisionResponse] = Field(default_factory=list)
    transitos_em_julgado: list[FinalJudgmentResponse] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)
    gerado_em: str
    atualizado_em: str


class DefenseThesesGenerateRequest(BaseModel):
    top_k: int = 36
    max_teses: int = 8
    regenerar: bool = False


class DefenseEvidenceResponse(BaseModel):
    fonte_id: str
    texto: str
    paginas: list[int]
    chunk_index: int | None
    origem: str
    confianca_fonte: str


class DefenseLegalBasisResponse(BaseModel):
    fonte_id: str
    referencia: str
    url: str


class DefenseThesisResponse(BaseModel):
    catalogo_id: str
    titulo: str
    categoria: str
    questao_juridica: str
    analise: str
    prioridade: int
    nivel_suporte: Literal["inicial", "amplo", "controvertido"]
    fontes_favoraveis: list[DefenseEvidenceResponse] = Field(default_factory=list)
    fontes_contrarias: list[DefenseEvidenceResponse] = Field(default_factory=list)
    fundamentos_juridicos: list[DefenseLegalBasisResponse] = Field(default_factory=list)
    pontos_para_confirmar: list[str] = Field(default_factory=list)
    revisao_necessaria: bool


class DefenseCatalogSourceResponse(BaseModel):
    id: str
    autoridade: str
    titulo: str
    referencia: str
    url: str


class DefenseThesesResponse(BaseModel):
    processo_id: str
    status: Literal["concluido", "sem_teses_sustentadas", "sem_fontes_confiaveis"]
    versao: str
    versao_catalogo: str
    modelo: str
    fallback_usado: bool
    modo_busca: Literal["hibrida", "lexical"]
    teses: list[DefenseThesisResponse] = Field(default_factory=list)
    lacunas_gerais: list[str] = Field(default_factory=list)
    fontes_juridicas: list[DefenseCatalogSourceResponse] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)
    gerado_em: str
    atualizado_em: str


class ErrorResponse(BaseModel):
    error: str
    detail: str
