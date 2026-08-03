from __future__ import annotations

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


class StructuredTestimonyResponse(BaseModel):
    ordem: int
    tipo_documento: str
    titulo: str
    pessoa: str | None
    papel: Literal["vitima", "testemunha", "condutor", "reu", "declarante", "outro"]
    fase: Literal["inquerito", "juizo", "outro"]
    cobertura: Literal["integral", "parcial"]
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


class ErrorResponse(BaseModel):
    error: str
    detail: str
