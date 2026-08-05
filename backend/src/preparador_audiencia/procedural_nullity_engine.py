from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from preparador_audiencia.legal_catalog import (
    PROCEDURAL_NULLITY_TOPIC_IDS,
    LegalRequirement,
    LegalTopic,
    load_legal_topic,
)
from preparador_audiencia.llm import LLMAnswer, llm_client_from_spec
from preparador_audiencia.nullity_analysis_repository import (
    NULLITY_ANALYSIS_SCHEMA_VERSION,
    NullityAnalysisRecord,
    NullityAnalysisRepository,
)
from preparador_audiencia.prompt_security import partition_adversarial_sources
from preparador_audiencia.prompts.procedural_nullities import (
    build_procedural_nullity_prompts,
)
from preparador_audiencia.retrieval import (
    search_process_queries_configured,
    search_process_queries_lexical,
)
from preparador_audiencia.search import SearchResult
from preparador_audiencia.settings import (
    nullity_fallback_llm_from_environment,
    primary_llm_from_environment,
)

Conclusion = Literal[
    "configurada",
    "indicios_suficientes",
    "nao_configurada",
    "inconclusiva",
]
RequirementResult = Literal[
    "observado",
    "nao_observado",
    "nao_localizado",
    "nao_aplicavel",
]

MAX_SOURCES = 32
MAX_SOURCE_CHARS = 4500

CONCLUSION_LABELS: dict[Conclusion, str] = {
    "configurada": "Nulidade configurada pelos elementos localizados",
    "indicios_suficientes": "Indicios suficientes para aprofundar a arguicao",
    "nao_configurada": "Nulidade nao configurada nos elementos localizados",
    "inconclusiva": "Analise inconclusiva",
}


class ProceduralNullityUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProceduralNullityResult:
    topic: LegalTopic
    conclusion: Conclusion
    confidence: str
    summary: str
    requirements: tuple[dict[str, object], ...]
    next_steps: tuple[str, ...]
    gaps: tuple[str, ...]
    process_sources: tuple[dict[str, object], ...]
    warnings: tuple[str, ...]
    model: str
    fallback_used: bool
    search_mode: str

    def payload(self) -> dict[str, object]:
        return {
            "titulo": self.topic.title,
            "escopo": self.topic.scope,
            "conclusao_rotulo": CONCLUSION_LABELS[self.conclusion],
            "confianca": self.confidence,
            "resumo": self.summary,
            "requisitos": list(self.requirements),
            "providencias": list(self.next_steps),
            "lacunas": list(self.gaps),
            "fontes_processuais": list(self.process_sources),
            "fontes_juridicas": [
                {
                    "id": source.id,
                    "autoridade": source.authority,
                    "tipo": source.kind,
                    "titulo": source.title,
                    "referencia": source.reference,
                    "url": source.url,
                    "resumo": source.summary,
                }
                for source in self.topic.sources
            ],
            "avisos": list(self.warnings),
        }


class _RawEvidence(BaseModel):
    fonte_id: str
    trecho_exato: str


class _RawRequirement(BaseModel):
    id: str
    resultado: str
    justificativa: str
    evidencias: list[_RawEvidence] = Field(default_factory=list)
    fontes_juridicas: list[str] = Field(default_factory=list)


class _RawAnalysis(BaseModel):
    resumo: str
    confianca: str
    requisitos: list[_RawRequirement]
    providencias: list[str] = Field(default_factory=list)
    lacunas: list[str] = Field(default_factory=list)


def generate_procedural_nullity(
    processo_id: str,
    topic_id: str,
    repository: NullityAnalysisRepository,
    *,
    top_k: int = 24,
    regenerate: bool = False,
    primary_model: str | None = None,
    fallback_model: str | None = None,
) -> NullityAnalysisRecord:
    topic = _load_procedural_topic(topic_id)
    cached = repository.get(processo_id, topic_id)
    if (
        cached is not None
        and cached.schema_version == NULLITY_ANALYSIS_SCHEMA_VERSION
        and cached.catalog_version == topic.version
        and not regenerate
    ):
        return cached

    search_mode = "hibrida"
    try:
        retrieved = search_process_queries_configured(
            processo_id=processo_id,
            queries=[(query, 1.0) for query in topic.search_queries],
            top_k=top_k,
        )
    except Exception:
        search_mode = "lexical"
        retrieved = search_process_queries_lexical(
            processo_id=processo_id,
            queries=[(query, 1.0) for query in topic.search_queries],
            top_k=top_k,
        )

    try:
        result = analyze_procedural_nullity_sources(
            topic,
            retrieved,
            primary_model=primary_model,
            fallback_model=fallback_model,
            search_mode=search_mode,
        )
    except RuntimeError as exc:
        raise ProceduralNullityUnavailableError(str(exc)) from exc
    return repository.save(
        processo_id,
        topic_id,
        catalog_version=topic.version,
        conclusion=result.conclusion,
        payload=result.payload(),
        model=result.model,
        fallback_used=result.fallback_used,
        search_mode=result.search_mode,
    )


def analyze_procedural_nullity_sources(
    topic: LegalTopic,
    retrieved_sources: list[SearchResult],
    *,
    primary_model: str | None = None,
    fallback_model: str | None = None,
    search_mode: str = "hibrida",
) -> ProceduralNullityResult:
    if topic.id not in PROCEDURAL_NULLITY_TOPIC_IDS:
        raise ValueError(f"Tema nao pertence ao motor geral de nulidades: {topic.id}")
    sources, warnings = _prepare_sources(retrieved_sources)
    if not sources:
        return _system_result(
            topic,
            "Nenhum trecho com extracao confiavel foi localizado para este tema.",
            warnings,
            search_mode=search_mode,
        )
    if not _contains_topic_evidence(topic, sources):
        return _system_result(
            topic,
            "Os trechos recuperados nao demonstram a existencia do ato processual analisado.",
            warnings,
            search_mode=search_mode,
            process_sources=sources,
        )

    prompt_sources = [
        {"id": source["id"], "pagina": source["pagina"], "texto": source["texto"]}
        for source in sources
    ]
    system_prompt, user_prompt = build_procedural_nullity_prompts(
        topic,
        prompt_sources,
    )
    raw, answer, fallback_used = _complete_with_fallback(
        system_prompt,
        user_prompt,
        primary_model or primary_llm_from_environment(),
        fallback_model or nullity_fallback_llm_from_environment(),
    )
    requirements = _sanitize_requirements(raw, topic, sources)
    conclusion = _resolve_conclusion(topic, requirements)
    confidence = _resolve_confidence(raw.confianca, conclusion, requirements)
    summary = _build_summary(conclusion, requirements)
    gaps = _merge_gaps(raw.lacunas, requirements)
    next_steps = tuple(_clean_items(raw.providencias, limit=8))
    return ProceduralNullityResult(
        topic=topic,
        conclusion=conclusion,
        confidence=confidence,
        summary=summary,
        requirements=requirements,
        next_steps=next_steps,
        gaps=gaps,
        process_sources=tuple(sources),
        warnings=tuple(
            [
                *warnings,
                (
                    "A conclusao foi calculada pelo servidor. Abra os trechos citados "
                    "antes de usar a analise em uma manifestacao."
                ),
            ]
        ),
        model=answer.model,
        fallback_used=fallback_used,
        search_mode=search_mode,
    )


def _load_procedural_topic(topic_id: str) -> LegalTopic:
    if topic_id not in PROCEDURAL_NULLITY_TOPIC_IDS:
        raise ValueError(f"Tema de nulidade desconhecido: {topic_id}")
    return load_legal_topic(topic_id)


def _prepare_sources(
    retrieved_sources: list[SearchResult],
) -> tuple[list[dict[str, object]], list[str]]:
    safe, flagged = partition_adversarial_sources(retrieved_sources)
    reliable = [
        source for source in safe if source.source_confidence in {"alta", "media"}
    ]
    low_confidence = [
        source for source in safe if source.source_confidence not in {"alta", "media"}
    ]
    warnings = []
    if flagged:
        warnings.append(
            f"{len(flagged)} trecho(s) com padrao adversarial foram bloqueados."
        )
    if low_confidence:
        warnings.append(
            f"{len(low_confidence)} trecho(s) com OCR baixo ou desconhecido foram ignorados."
        )
    sources = []
    seen: set[tuple[int, int, str]] = set()
    for source in reliable:
        text = source.text.strip()[:MAX_SOURCE_CHARS]
        key = (source.page_number, source.chunk_index, _normalize(text))
        if not text or key in seen:
            continue
        seen.add(key)
        sources.append(
            {
                "id": f"fonte-p{source.page_number}-c{source.chunk_index}",
                "texto": text,
                "pagina": source.page_number,
                "chunk_index": source.chunk_index,
                "tipo_documento": source.document_type,
                "confianca_fonte": source.source_confidence,
            }
        )
    if len(sources) > MAX_SOURCES:
        warnings.append(
            f"Somente as {MAX_SOURCES} fontes mais relevantes foram enviadas ao modelo."
        )
    return sources[:MAX_SOURCES], warnings


def _contains_topic_evidence(
    topic: LegalTopic,
    sources: list[dict[str, object]],
) -> bool:
    if not topic.evidence_terms:
        return True
    combined = "\n".join(_normalize(str(source["texto"])) for source in sources)
    return any(_normalize(term) in combined for term in topic.evidence_terms)


def _complete_with_fallback(
    system_prompt: str,
    user_prompt: str,
    primary_spec: str,
    fallback_spec: str,
) -> tuple[_RawAnalysis, LLMAnswer, bool]:
    primary_answer, primary_raw, primary_error = _try_complete(
        primary_spec,
        system_prompt,
        user_prompt,
    )
    if primary_raw is not None:
        return primary_raw, primary_answer, False
    fallback_answer, fallback_raw, fallback_error = _try_complete(
        fallback_spec,
        system_prompt,
        user_prompt,
    )
    if fallback_raw is not None:
        return fallback_raw, fallback_answer, True
    raise RuntimeError(
        "Gemini falhou: "
        f"{primary_error or 'resposta vazia'}; Groq falhou: "
        f"{fallback_error or 'resposta vazia'}"
    )


def _try_complete(
    model_spec: str,
    system_prompt: str,
    user_prompt: str,
) -> tuple[LLMAnswer, _RawAnalysis | None, str | None]:
    try:
        answer = llm_client_from_spec(model_spec).complete(system_prompt, user_prompt)
    except Exception as exc:
        return LLMAnswer(model_spec, "", 0, error=str(exc)), None, str(exc)
    if answer.error or not answer.answer:
        return answer, None, answer.error or "resposta vazia"
    try:
        return answer, _parse_output(answer.answer), None
    except (ValueError, json.JSONDecodeError) as exc:
        return answer, None, f"resposta fora do formato esperado: {exc}"


def _parse_output(answer: str) -> _RawAnalysis:
    start = answer.find("{")
    end = answer.rfind("}")
    if start < 0 or end < start:
        raise ValueError("JSON nao encontrado")
    return _RawAnalysis.model_validate(json.loads(answer[start : end + 1]))


def _sanitize_requirements(
    raw: _RawAnalysis,
    topic: LegalTopic,
    sources: list[dict[str, object]],
) -> tuple[dict[str, object], ...]:
    source_map = {str(source["id"]): source for source in sources}
    legal_ids = {source.id for source in topic.sources}
    raw_by_id = {item.id: item for item in raw.requisitos}
    output = []
    for requirement in topic.requirements:
        item = raw_by_id.get(requirement.id)
        if item is None:
            output.append(_missing_requirement(requirement))
            continue
        result = _normalize_choice(
            item.resultado,
            {"observado", "nao_observado", "nao_localizado", "nao_aplicavel"},
            "nao_localizado",
        )
        evidence = _validated_evidence(item.evidencias, source_map)
        justification = item.justificativa.strip()
        if result in {"observado", "nao_observado"} and not evidence:
            result = "nao_localizado"
            justification = (
                "O resultado proposto nao possuia trecho literal validado no processo."
            )
        selected_legal_ids = [
            source_id
            for source_id in dict.fromkeys(item.fontes_juridicas)
            if source_id in legal_ids
        ]
        output.append(
            {
                "id": requirement.id,
                "categoria": requirement.category,
                "rotulo": requirement.label,
                "condicao": requirement.condition,
                "resultado": result,
                "justificativa": justification,
                "evidencias": evidence,
                "fontes_juridicas": selected_legal_ids
                or list(requirement.legal_source_ids),
                "decisivo_sem_prejuizo": requirement.decisive_without_prejudice,
            }
        )
    return tuple(output)


def _validated_evidence(
    raw_evidence: list[_RawEvidence],
    source_map: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    output = []
    seen: set[tuple[str, str]] = set()
    for raw in raw_evidence:
        source = source_map.get(raw.fonte_id.strip())
        claimed = raw.trecho_exato.strip().strip('"').strip()
        if source is None or not claimed:
            continue
        source_text = str(source["texto"])
        start = source_text.casefold().find(claimed.casefold())
        if start < 0:
            continue
        exact = source_text[start : start + len(claimed)]
        key = (str(source["id"]), exact.casefold())
        if key in seen:
            continue
        seen.add(key)
        output.append(
            {
                "fonte_id": source["id"],
                "trecho": exact,
                "pagina": source["pagina"],
                "chunk_index": source["chunk_index"],
                "tipo_documento": source["tipo_documento"],
                "confianca_fonte": source["confianca_fonte"],
            }
        )
    return output


def _missing_requirement(requirement: LegalRequirement) -> dict[str, object]:
    return {
        "id": requirement.id,
        "categoria": requirement.category,
        "rotulo": requirement.label,
        "condicao": requirement.condition,
        "resultado": "nao_localizado",
        "justificativa": "Nao foi localizada informacao suficiente para este requisito.",
        "evidencias": [],
        "fontes_juridicas": list(requirement.legal_source_ids),
        "decisivo_sem_prejuizo": requirement.decisive_without_prejudice,
    }


def _resolve_conclusion(
    topic: LegalTopic,
    requirements: tuple[dict[str, object], ...],
) -> Conclusion:
    applicability = _by_category(requirements, "aplicabilidade")
    applicable = [item for item in applicability if _supported_result(item, "observado")]
    explicitly_not_applicable = [
        item
        for item in applicability
        if item["resultado"] in {"nao_observado", "nao_aplicavel"}
        and item["evidencias"]
    ]
    if applicability and not applicable:
        return "nao_configurada" if explicitly_not_applicable else "inconclusiva"

    validity = _by_category(requirements, "validade")
    violations = [
        item for item in validity if _supported_result(item, "nao_observado")
    ]
    prejudice = [
        item
        for item in _by_category(requirements, "prejuizo")
        if _supported_result(item, "observado")
    ]
    counterweights = [
        item
        for item in _by_category(requirements, "contrapeso")
        if _supported_result(item, "observado")
    ]
    decisive = any(bool(item["decisivo_sem_prejuizo"]) for item in violations)
    if violations:
        if (decisive or prejudice) and not counterweights:
            return "configurada"
        return "indicios_suficientes"
    if validity and all(
        item["resultado"] in {"observado", "nao_aplicavel"} for item in validity
    ):
        return "nao_configurada"
    return "inconclusiva"


def _by_category(
    requirements: tuple[dict[str, object], ...],
    category: str,
) -> list[dict[str, object]]:
    return [item for item in requirements if item["categoria"] == category]


def _supported_result(item: dict[str, object], result: str) -> bool:
    return item["resultado"] == result and bool(item["evidencias"])


def _resolve_confidence(
    raw_confidence: str,
    conclusion: Conclusion,
    requirements: tuple[dict[str, object], ...],
) -> str:
    confidence = _normalize_choice(
        raw_confidence,
        {"alta", "media", "baixa"},
        "baixa",
    )
    if conclusion == "inconclusiva":
        return "baixa"
    if conclusion == "nao_configurada":
        return _cap_confidence(confidence, "media")
    cited = [
        evidence
        for item in requirements
        if item["resultado"] in {"observado", "nao_observado"}
        for evidence in item["evidencias"]
    ]
    if not cited:
        return "baixa"
    if any(evidence["confianca_fonte"] == "media" for evidence in cited):
        return _cap_confidence(confidence, "media")
    return confidence


def _build_summary(
    conclusion: Conclusion,
    requirements: tuple[dict[str, object], ...],
) -> str:
    violations = [
        str(item["rotulo"])
        for item in _by_category(requirements, "validade")
        if _supported_result(item, "nao_observado")
    ]
    prejudice = [
        str(item["rotulo"])
        for item in _by_category(requirements, "prejuizo")
        if _supported_result(item, "observado")
    ]
    counterweights = [
        str(item["rotulo"])
        for item in _by_category(requirements, "contrapeso")
        if _supported_result(item, "observado")
    ]
    parts = [CONCLUSION_LABELS[conclusion] + "."]
    if violations:
        parts.append("Falhas documentadas: " + "; ".join(violations) + ".")
    if prejudice:
        parts.append("Prejuizo ou impacto documentado: " + "; ".join(prejudice) + ".")
    if counterweights:
        parts.append(
            "Elementos que reduzem ou controvertem o efeito: "
            + "; ".join(counterweights)
            + "."
        )
    if conclusion == "inconclusiva":
        parts.append("Faltam trechos seguros para confirmar os requisitos essenciais.")
    return " ".join(parts)


def _merge_gaps(
    raw_gaps: list[str],
    requirements: tuple[dict[str, object], ...],
) -> tuple[str, ...]:
    items = _clean_items(raw_gaps, limit=8)
    for requirement in requirements:
        if requirement["resultado"] != "nao_localizado":
            continue
        gap = f"Confirmar no processo: {requirement['rotulo']}."
        if gap not in items:
            items.append(gap)
        if len(items) >= 12:
            break
    return tuple(items)


def _clean_items(values: list[str], *, limit: int) -> list[str]:
    output = []
    for value in values:
        item = " ".join(value.strip().split())
        if item and item not in output:
            output.append(item[:500])
        if len(output) >= limit:
            break
    return output


def _system_result(
    topic: LegalTopic,
    summary: str,
    warnings: list[str],
    *,
    search_mode: str,
    process_sources: list[dict[str, object]] | None = None,
) -> ProceduralNullityResult:
    requirements = tuple(_missing_requirement(item) for item in topic.requirements)
    return ProceduralNullityResult(
        topic=topic,
        conclusion="inconclusiva",
        confidence="baixa",
        summary=summary,
        requirements=requirements,
        next_steps=("Localizar o ato processual e seus documentos de cumprimento.",),
        gaps=tuple(
            f"Confirmar no processo: {requirement.label}."
            for requirement in topic.requirements
        ),
        process_sources=tuple(process_sources or []),
        warnings=tuple(warnings),
        model="sistema",
        fallback_used=False,
        search_mode=search_mode,
    )


def _normalize_choice(value: str, allowed: set[str], fallback: str) -> str:
    normalized = _normalize(value).replace(" ", "_")
    return normalized if normalized in allowed else fallback


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return " ".join(without_accents.split())


def _cap_confidence(confidence: str, maximum: str) -> str:
    levels = {"baixa": 0, "media": 1, "alta": 2}
    return min((confidence, maximum), key=lambda item: levels[item])
