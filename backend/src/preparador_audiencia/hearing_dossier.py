from __future__ import annotations

import json
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from preparador_audiencia.hearing_dossier_facts import detect_key_events
from preparador_audiencia.hearing_dossier_repository import (
    DOSSIER_SECTION_KEYS,
    HearingDossierRecord,
    HearingDossierRepository,
)
from preparador_audiencia.llm import LLMAnswer, llm_client_from_spec
from preparador_audiencia.prompt_security import partition_adversarial_sources
from preparador_audiencia.prompts.hearing_dossier import (
    SECTION_QUERIES,
    build_section_prompts,
)
from preparador_audiencia.retrieval import (
    search_process_pattern_anchors,
    search_process_queries_configured,
    search_process_queries_lexical,
)
from preparador_audiencia.search import SearchResult
from preparador_audiencia.settings import (
    dossier_fallback_llm_from_environment,
    primary_llm_from_environment,
)

EventType = Literal[
    "data_fato",
    "nascimento_reu",
    "recebimento_denuncia",
    "suspensao_inicio",
    "suspensao_fim",
    "prisao",
    "liberdade",
    "audiencia",
    "outro",
]

EVENT_TYPES = {
    "data_fato",
    "nascimento_reu",
    "recebimento_denuncia",
    "suspensao_inicio",
    "suspensao_fim",
    "prisao",
    "liberdade",
    "audiencia",
    "outro",
}
REQUIRED_EVENT_GROUPS = {
    "data_fato": ("Data, horario e local do fato", {"data_fato"}),
    "nascimento_reu": ("Data de nascimento do reu", {"nascimento_reu"}),
    "recebimento_denuncia": (
        "Data do recebimento da denuncia ou queixa",
        {"recebimento_denuncia"},
    ),
    "suspensao_processo": (
        "Existencia e periodo de eventual suspensao do processo",
        {"suspensao_inicio", "suspensao_fim"},
    ),
}
MAX_SECTION_ITEMS = 60
MAX_EXCERPTS_PER_TESTIMONY = 20
MIN_EXCERPT_CHARS = 25
MIN_EXCERPT_WORDS = 6
DETERMINISTIC_SINGLETON_EVENT_TYPES = {
    "data_fato",
    "nascimento_reu",
    "recebimento_denuncia",
    "prisao",
}

SECTION_PATTERN_ANCHORS: dict[str, tuple[tuple[str, int], ...]] = {
    "marcos_essenciais": (
        ("i dos fatos", 2),
        ("nascido aos", 2),
        ("recebo a denuncia", 2),
        ("suspendo o processo", 2),
        ("auto de prisao em flagrante delito", 2),
        ("concedida a liberdade provisoria", 2),
        ("periodo do cumprimento da medida inicio", 2),
        ("liberdade provisoria", 2),
        ("redesignando a audiencia", 2),
        ("data e hora da audiencia", 3),
    ),
    "depoimentos": (
        ("em sede policial declarou", 2),
        ("em seus depoimentos", 2),
        ("termo de declaracao", 3),
        ("termo de declaracoes", 3),
        ("termo de depoimento", 5),
        ("termo de interrogatorio", 3),
    ),
    "contradicoes": (
        ("em sede policial declarou", 2),
        ("em seus depoimentos", 2),
        ("termo de declaracao", 3),
        ("termo de declaracoes", 3),
        ("termo de depoimento", 5),
        ("termo de interrogatorio", 3),
    ),
}


class DossierSectionGenerationError(RuntimeError):
    def __init__(self, message: str, retrieval_ms: int, generation_ms: int) -> None:
        super().__init__(message)
        self.retrieval_ms = retrieval_ms
        self.generation_ms = generation_ms


class _RawKeyEvent(BaseModel):
    tipo: str
    rotulo: str
    valor: str
    pessoa: str = ""
    descricao: str = ""
    fonte_ids: list[str] = Field(default_factory=list)


class _RawKeyEvents(BaseModel):
    itens: list[_RawKeyEvent] = Field(default_factory=list)
    lacunas: list[str] = Field(default_factory=list)


class _RawExcerpt(BaseModel):
    trecho_exato: str
    fonte_id: str


class _RawTestimony(BaseModel):
    pessoa: str
    papel: str
    fase: str
    cobertura: str = "nao_determinada"
    inicio_localizado: bool = False
    fim_localizado: bool = False
    trechos: list[_RawExcerpt] = Field(default_factory=list)


class _RawTestimonies(BaseModel):
    itens: list[_RawTestimony] = Field(default_factory=list)
    lacunas: list[str] = Field(default_factory=list)


class _RawContradiction(BaseModel):
    titulo: str
    pessoa_a: str
    afirmacao_a: _RawExcerpt
    pessoa_b: str
    afirmacao_b: _RawExcerpt
    explicacao: str
    relevancia_audiencia: str


class _RawContradictions(BaseModel):
    itens: list[_RawContradiction] = Field(default_factory=list)
    lacunas: list[str] = Field(default_factory=list)


RAW_MODELS: dict[str, type[BaseModel]] = {
    "marcos_essenciais": _RawKeyEvents,
    "depoimentos": _RawTestimonies,
    "contradicoes": _RawContradictions,
}


@dataclass(frozen=True)
class SectionGenerationResult:
    payload: dict[str, object]
    model: str | None
    fallback_used: bool
    retrieval_ms: int | None = None
    generation_ms: int | None = None


def generate_hearing_dossier(
    processo_id: str,
    repository: HearingDossierRepository,
    *,
    top_k: int = 18,
    primary_model: str | None = None,
    fallback_model: str | None = None,
    lexical_only: bool = False,
    regenerate: bool = False,
    section_delay_seconds: float = 0.0,
) -> HearingDossierRecord:
    dossier = repository.prepare(processo_id, regenerate=regenerate)
    if dossier.status == "concluido" and not regenerate:
        return dossier

    repository.mark_processing(processo_id)
    prior_sections = {
        section.key: section.payload
        for section in dossier.sections
        if section.status == "concluido"
    }
    for section_key in DOSSIER_SECTION_KEYS:
        current = repository.get(processo_id)
        if current is None:
            raise RuntimeError("dossie desapareceu durante a geracao")
        section = next(item for item in current.sections if item.key == section_key)
        if section.status == "concluido":
            prior_sections[section_key] = section.payload
            continue

        repository.mark_section_processing(processo_id, section_key)
        try:
            generated = generate_dossier_section(
                processo_id,
                section_key,
                prior_sections=prior_sections,
                top_k=top_k,
                primary_model=primary_model,
                fallback_model=fallback_model,
                lexical_only=lexical_only,
            )
        except RuntimeError as exc:
            repository.mark_section_error(
                processo_id,
                section_key,
                str(exc),
                retrieval_ms=getattr(exc, "retrieval_ms", None),
                generation_ms=getattr(exc, "generation_ms", None),
            )
            _delay_before_remaining_section(
                repository,
                processo_id,
                section_key,
                section_delay_seconds,
            )
            continue
        repository.save_section(
            processo_id,
            section_key,
            generated.payload,
            model=generated.model,
            fallback_used=generated.fallback_used,
            retrieval_ms=generated.retrieval_ms,
            generation_ms=generated.generation_ms,
        )
        prior_sections[section_key] = generated.payload
        _delay_before_remaining_section(
            repository,
            processo_id,
            section_key,
            section_delay_seconds,
        )
    return repository.finish(processo_id)


def generate_dossier_section(
    processo_id: str,
    section_key: str,
    *,
    prior_sections: dict[str, dict[str, object]] | None = None,
    top_k: int = 18,
    primary_model: str | None = None,
    fallback_model: str | None = None,
    lexical_only: bool = False,
) -> SectionGenerationResult:
    if section_key not in DOSSIER_SECTION_KEYS:
        raise ValueError(f"Secao desconhecida: {section_key}")
    retrieval_started = time.perf_counter()
    retrieved_sources = _retrieve_diverse_sources(
        processo_id,
        section_key,
        top_k=top_k,
        lexical_only=lexical_only,
    )
    retrieval_ms = _elapsed_ms(retrieval_started)
    reliable_sources, warnings = _filter_sources(retrieved_sources)
    if not reliable_sources:
        return SectionGenerationResult(
            payload=_empty_payload(section_key, warnings),
            model="sistema",
            fallback_used=False,
            retrieval_ms=retrieval_ms,
            generation_ms=0,
        )

    system_prompt, user_prompt = build_section_prompts(
        section_key,
        reliable_sources,
        prior_sections or {},
    )
    generation_started = time.perf_counter()
    try:
        raw, answer, fallback_used = _complete_with_fallback(
            section_key=section_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            primary_spec=primary_model or primary_llm_from_environment(),
            fallback_spec=fallback_model or dossier_fallback_llm_from_environment(),
        )
    except RuntimeError as exc:
        raise DossierSectionGenerationError(
            str(exc),
            retrieval_ms,
            _elapsed_ms(generation_started),
        ) from exc
    generation_ms = _elapsed_ms(generation_started)
    payload = _sanitize_payload(section_key, raw, reliable_sources, warnings)
    return SectionGenerationResult(
        payload=payload,
        model=answer.model,
        fallback_used=fallback_used,
        retrieval_ms=retrieval_ms,
        generation_ms=generation_ms,
    )


def _complete_with_fallback(
    *,
    section_key: str,
    system_prompt: str,
    user_prompt: str,
    primary_spec: str,
    fallback_spec: str,
) -> tuple[BaseModel, LLMAnswer, bool]:
    model_type = RAW_MODELS[section_key]
    primary_answer, primary_payload, primary_error = _try_complete(
        primary_spec,
        system_prompt,
        user_prompt,
        model_type,
    )
    if primary_payload is not None:
        return primary_payload, primary_answer, False

    fallback_answer, fallback_payload, fallback_error = _try_complete(
        fallback_spec,
        system_prompt,
        user_prompt,
        model_type,
    )
    if fallback_payload is not None:
        return fallback_payload, fallback_answer, True

    raise RuntimeError(
        "Gemini falhou: "
        f"{primary_error or 'resposta vazia'}; Groq falhou: "
        f"{fallback_error or 'resposta vazia'}"
    )


def _try_complete(
    model_spec: str,
    system_prompt: str,
    user_prompt: str,
    model_type: type[BaseModel],
) -> tuple[LLMAnswer, BaseModel | None, str | None]:
    try:
        answer = llm_client_from_spec(model_spec).complete(system_prompt, user_prompt)
    except Exception as exc:
        return LLMAnswer(model_spec, "", 0, error=str(exc)), None, str(exc)
    if answer.error or not answer.answer:
        return answer, None, answer.error or "resposta vazia"
    try:
        payload = _parse_json(answer.answer)
        return answer, model_type.model_validate(payload), None
    except (ValueError, json.JSONDecodeError, ValidationError) as exc:
        return answer, None, f"resposta fora do formato esperado: {exc}"


def _parse_json(answer: str) -> dict[str, object]:
    start = answer.find("{")
    end = answer.rfind("}")
    if start < 0 or end < start:
        raise ValueError("JSON nao encontrado")
    payload = json.loads(answer[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("objeto JSON esperado")
    return payload


def _sanitize_payload(
    section_key: str,
    raw: BaseModel,
    sources: list[SearchResult],
    warnings: list[str],
) -> dict[str, object]:
    if section_key == "marcos_essenciais":
        return _sanitize_key_events(raw, sources, warnings)
    if section_key == "depoimentos":
        return _sanitize_testimonies(raw, sources, warnings)
    return _sanitize_contradictions(raw, sources, warnings)


def _sanitize_key_events(
    raw: BaseModel,
    sources: list[SearchResult],
    warnings: list[str],
) -> dict[str, object]:
    assert isinstance(raw, _RawKeyEvents)
    source_map = _source_map(sources)
    items: list[dict[str, object]] = []
    seen: set[tuple[object, ...]] = set()
    found_types: set[str] = set()
    for detected in detect_key_events(sources):
        reference = _source_reference(detected.source, detected.value)
        key = (
            detected.event_type,
            detected.value.casefold(),
            "",
            (reference["pagina"],),
        )
        if key in seen:
            continue
        seen.add(key)
        found_types.add(detected.event_type)
        items.append(
            {
                "tipo": detected.event_type,
                "rotulo": detected.label,
                "valor": detected.value,
                "pessoa": None,
                "descricao": detected.description,
                "fontes": [reference],
            }
        )
    for item in raw.itens[:MAX_SECTION_ITEMS]:
        item_sources = _sources_for_ids(item.fonte_ids, source_map)
        claimed_value = item.valor.strip()
        value = _first_exact_excerpt(item_sources, claimed_value)
        if not item_sources or not value:
            continue
        source_refs = [_source_reference(source, source.text) for source in item_sources]
        event_type = item.tipo.strip().lower()
        if event_type not in EVENT_TYPES:
            event_type = "outro"
        if not _event_type_supported(event_type, item_sources):
            continue
        if (
            event_type in DETERMINISTIC_SINGLETON_EVENT_TYPES
            and event_type in found_types
        ):
            continue
        key = (
            event_type,
            value.casefold(),
            item.pessoa.strip().casefold(),
            tuple(reference["pagina"] for reference in source_refs),
        )
        if key in seen:
            continue
        seen.add(key)
        found_types.add(event_type)
        items.append(
            {
                "tipo": event_type,
                "rotulo": item.rotulo.strip() or _event_label(event_type),
                "valor": value,
                "pessoa": _validated_person(item.pessoa, item_sources),
                "descricao": item.descricao.strip() or None,
                "fontes": source_refs,
            }
        )

    normalized_missing: list[dict[str, str]] = []
    for key, (label, accepted_types) in REQUIRED_EVENT_GROUPS.items():
        if not found_types.intersection(accepted_types):
            normalized_missing.append(
                {
                    "campo": key,
                    "rotulo": label,
                    "motivo": "Nao localizado com fonte suficiente no processo.",
                }
            )
    seen_other_gaps: set[str] = set()
    for gap in _clean_strings(raw.lacunas):
        matched_field = _event_field_for_gap(gap)
        if matched_field is not None:
            if matched_field in REQUIRED_EVENT_GROUPS or matched_field in found_types:
                continue
            normalized_missing.append(
                {
                    "campo": matched_field,
                    "rotulo": gap,
                    "motivo": "Informacao a confirmar.",
                }
            )
            continue
        normalized = _fold_identifier(gap)
        if normalized in seen_other_gaps:
            continue
        seen_other_gaps.add(normalized)
        normalized_missing.append(
            {"campo": "outro", "rotulo": gap, "motivo": "Informacao a confirmar."}
        )
    return {
        "itens": items,
        "campos_para_confirmar": normalized_missing,
        "avisos": _unique_strings(
            [
                *warnings,
                "Os marcos foram extraidos para conferencia e ainda nao calculam prescricao.",
            ]
        ),
    }


def _sanitize_testimonies(
    raw: BaseModel,
    sources: list[SearchResult],
    warnings: list[str],
) -> dict[str, object]:
    assert isinstance(raw, _RawTestimonies)
    source_map = _source_map(sources)
    items: list[dict[str, object]] = []
    invalid_quotes = 0
    short_quotes = 0
    downgraded_integral = False
    for item in raw.itens[:MAX_SECTION_ITEMS]:
        excerpts: list[dict[str, object]] = []
        source_positions: list[tuple[int, int]] = []
        item_invalid_quotes = 0
        seen_excerpts: set[tuple[int, int, str]] = set()
        for excerpt in item.trechos[:MAX_EXCERPTS_PER_TESTIMONY]:
            source = source_map.get(excerpt.fonte_id)
            exact = _exact_excerpt(source.text, excerpt.trecho_exato) if source else None
            if source is None or exact is None:
                invalid_quotes += 1
                item_invalid_quotes += 1
                continue
            if not _is_meaningful_excerpt(exact):
                short_quotes += 1
                continue
            excerpt_key = (
                source.page_number,
                source.chunk_index,
                exact.casefold(),
            )
            if excerpt_key in seen_excerpts:
                continue
            seen_excerpts.add(excerpt_key)
            excerpts.append(
                {
                    "texto": exact,
                    "fonte": _source_reference(source, exact),
                }
            )
            source_positions.append((source.page_number, source.chunk_index))
        if not excerpts:
            continue
        coverage = "parcial"
        if (
            item.cobertura.strip().lower() == "integral"
            and item.inicio_localizado
            and item.fim_localizado
            and item_invalid_quotes == 0
            and _positions_are_continuous(source_positions)
        ):
            coverage = "integral"
        elif item.cobertura.strip().lower() == "integral":
            downgraded_integral = True
        items.append(
            {
                "pessoa": _validated_person(
                    item.pessoa,
                    [
                        source_map[excerpt.fonte_id]
                        for excerpt in item.trechos
                        if excerpt.fonte_id in source_map
                    ],
                )
                or "Pessoa nao identificada",
                "papel": _normalized_choice(
                    item.papel,
                    {"vitima", "testemunha", "reu", "informante", "outro"},
                    "outro",
                ),
                "fase": _normalized_choice(
                    item.fase,
                    {"inquerito", "juizo", "outro"},
                    "outro",
                ),
                "cobertura": coverage,
                "trechos": excerpts,
            }
        )
    section_warnings = list(warnings)
    if invalid_quotes:
        section_warnings.append(
            f"{invalid_quotes} trecho(s) sugerido(s) pelo modelo foram descartados por nao "
            "coincidirem literalmente com as fontes."
        )
    if short_quotes:
        section_warnings.append(
            f"{short_quotes} trecho(s) curto(s) ou sem contexto foram descartados para "
            "evitar transcricoes pouco uteis."
        )
    if downgraded_integral:
        section_warnings.append(
            "Uma transcricao indicada como integral foi marcada como parcial porque a "
            "continuidade entre inicio e fim nao pode ser comprovada."
        )
    section_warnings.append(
        "As falas exibidas sao trechos literais recuperados; abra as paginas para conferir "
        "o depoimento completo."
    )
    return {
        "itens": items,
        "lacunas": _clean_strings(raw.lacunas),
        "avisos": _unique_strings(section_warnings),
    }


def _sanitize_contradictions(
    raw: BaseModel,
    sources: list[SearchResult],
    warnings: list[str],
) -> dict[str, object]:
    assert isinstance(raw, _RawContradictions)
    source_map = _source_map(sources)
    items: list[dict[str, object]] = []
    invalid_pairs = 0
    seen: set[tuple[str, str]] = set()
    for item in raw.itens[:MAX_SECTION_ITEMS]:
        source_a = source_map.get(item.afirmacao_a.fonte_id)
        source_b = source_map.get(item.afirmacao_b.fonte_id)
        excerpt_a = (
            _exact_excerpt(source_a.text, item.afirmacao_a.trecho_exato)
            if source_a
            else None
        )
        excerpt_b = (
            _exact_excerpt(source_b.text, item.afirmacao_b.trecho_exato)
            if source_b
            else None
        )
        if source_a is None or source_b is None or not excerpt_a or not excerpt_b:
            invalid_pairs += 1
            continue
        pair_key = (excerpt_a.casefold(), excerpt_b.casefold())
        if excerpt_a.casefold() == excerpt_b.casefold() or pair_key in seen:
            continue
        seen.add(pair_key)
        items.append(
            {
                "titulo": item.titulo.strip() or "Divergencia a conferir",
                "pessoa_a": item.pessoa_a.strip() or "Fonte A",
                "afirmacao_a": {
                    "texto": excerpt_a,
                    "fonte": _source_reference(source_a, excerpt_a),
                },
                "pessoa_b": item.pessoa_b.strip() or "Fonte B",
                "afirmacao_b": {
                    "texto": excerpt_b,
                    "fonte": _source_reference(source_b, excerpt_b),
                },
                "explicacao": item.explicacao.strip(),
                "relevancia_audiencia": item.relevancia_audiencia.strip(),
                "estado": "potencial",
            }
        )
    section_warnings = list(warnings)
    if invalid_pairs:
        section_warnings.append(
            f"{invalid_pairs} comparacao(oes) foram descartadas porque um dos trechos nao "
            "foi confirmado literalmente nas fontes."
        )
    section_warnings.append(
        "As divergencias sao potenciais e precisam de confirmacao profissional no contexto "
        "integral dos depoimentos e das provas."
    )
    return {
        "itens": items,
        "lacunas": _clean_strings(raw.lacunas),
        "avisos": _unique_strings(section_warnings),
    }


def _filter_sources(
    sources: list[SearchResult],
) -> tuple[list[SearchResult], list[str]]:
    safe_sources, flagged_sources = partition_adversarial_sources(sources)
    reliable = [
        source
        for source in safe_sources
        if source.source_confidence in {"alta", "media"}
    ]
    low_confidence = [
        source
        for source in safe_sources
        if source.source_confidence not in {"alta", "media"}
    ]
    warnings: list[str] = []
    if flagged_sources:
        pages = sorted({item.source.page_number for item in flagged_sources})
        warnings.append(
            "Trechos potencialmente adversariais foram ignorados nas paginas "
            + ", ".join(str(page) for page in pages)
            + "."
        )
    if low_confidence:
        pages = sorted({source.page_number for source in low_confidence})
        warnings.append(
            "Trechos de OCR com confianca insuficiente foram ignorados nas paginas "
            + ", ".join(str(page) for page in pages)
            + "."
        )
    return reliable, warnings


def _retrieve_diverse_sources(
    processo_id: str,
    section_key: str,
    *,
    top_k: int,
    lexical_only: bool,
) -> list[SearchResult]:
    if top_k <= 0:
        return []
    queries = SECTION_QUERIES[section_key]
    search = (
        search_process_queries_lexical
        if lexical_only
        else search_process_queries_configured
    )
    query_limit = max(4, min(top_k, _ceiling_division(top_k, len(queries)) * 2))
    ranked_groups = [
        search(
            processo_id=processo_id,
            queries=[(query, 1.0)],
            top_k=query_limit,
        )
        for query in queries
    ]
    anchor_limit = min(top_k, max(4, _ceiling_division(top_k * 5, 6)))
    anchored = search_process_pattern_anchors(
        processo_id,
        SECTION_PATTERN_ANCHORS[section_key],
        top_k=anchor_limit,
    )
    return _merge_source_groups([anchored, *_round_robin_groups(ranked_groups)], top_k)


def _round_robin_groups(
    groups: list[list[SearchResult]],
) -> list[list[SearchResult]]:
    if not groups:
        return []
    longest = max((len(group) for group in groups), default=0)
    return [
        [group[index] for group in groups if index < len(group)]
        for index in range(longest)
    ]


def _merge_source_groups(
    groups: list[list[SearchResult]],
    top_k: int,
) -> list[SearchResult]:
    merged: list[SearchResult] = []
    seen: set[tuple[int, int]] = set()
    for group in groups:
        for source in group:
            key = (source.page_number, source.chunk_index)
            if key in seen:
                continue
            seen.add(key)
            merged.append(source)
            if len(merged) >= top_k:
                return merged
    return merged


def _empty_payload(section_key: str, warnings: list[str]) -> dict[str, object]:
    warning = "Nao ha fontes confiaveis suficientes para estruturar esta secao."
    if section_key == "marcos_essenciais":
        return {
            "itens": [],
            "campos_para_confirmar": [
                {"campo": key, "rotulo": value[0], "motivo": warning}
                for key, value in REQUIRED_EVENT_GROUPS.items()
            ],
            "avisos": _unique_strings([*warnings, warning]),
        }
    return {
        "itens": [],
        "lacunas": [warning],
        "avisos": _unique_strings([*warnings, warning]),
    }


def _source_map(sources: list[SearchResult]) -> dict[str, SearchResult]:
    return {f"P{index}": source for index, source in enumerate(sources, start=1)}


def _sources_for_ids(
    source_ids: list[str],
    source_map: dict[str, SearchResult],
) -> list[SearchResult]:
    sources: list[SearchResult] = []
    seen: set[tuple[int, int]] = set()
    for source_id in source_ids:
        source = source_map.get(source_id)
        if source is None:
            continue
        key = (source.page_number, source.chunk_index)
        if key in seen:
            continue
        seen.add(key)
        sources.append(source)
    return sources


def _source_reference(source: SearchResult, excerpt: str) -> dict[str, object]:
    return {
        "pagina": source.page_number,
        "chunk_index": source.chunk_index,
        "tipo_documento": source.document_type,
        "confianca_fonte": source.source_confidence,
        "trecho": excerpt,
    }


def _exact_excerpt(source_text: str, claimed_excerpt: str) -> str | None:
    tokens = claimed_excerpt.strip().split()
    if not tokens:
        return None
    pattern = r"\s+".join(re.escape(token) for token in tokens)
    match = re.search(pattern, source_text, flags=re.IGNORECASE)
    return " ".join(match.group(0).split()) if match else None


def _first_exact_excerpt(
    sources: list[SearchResult],
    claimed_excerpt: str,
) -> str | None:
    for source in sources:
        if exact := _exact_excerpt(source.text, claimed_excerpt):
            return exact
    return None


def _validated_person(value: str, sources: list[SearchResult]) -> str | None:
    person = value.strip()
    if not person:
        return None
    if _first_exact_excerpt(sources, person):
        return person
    generic_roles = {
        "acusado",
        "documento",
        "informante",
        "laudo",
        "pericia",
        "reu",
        "testemunha",
        "vitima",
    }
    if any(role in person.casefold() for role in generic_roles):
        return person
    return None


def _positions_are_continuous(positions: list[tuple[int, int]]) -> bool:
    unique = sorted(set(positions))
    if not unique:
        return False
    for current, following in zip(unique, unique[1:], strict=False):
        same_page = following[0] == current[0] and following[1] == current[1] + 1
        next_page = following[0] == current[0] + 1 and following[1] == 0
        if not (same_page or next_page):
            return False
    return True


def _normalized_choice(value: str, allowed: set[str], default: str) -> str:
    normalized = _fold_choice(value)
    return normalized if normalized in allowed else default


def _event_label(event_type: str) -> str:
    return {
        "data_fato": "Data do fato",
        "nascimento_reu": "Nascimento do reu",
        "recebimento_denuncia": "Recebimento da denuncia",
        "suspensao_inicio": "Inicio da suspensao",
        "suspensao_fim": "Fim da suspensao",
        "prisao": "Prisao",
        "liberdade": "Liberdade",
        "audiencia": "Audiencia",
        "outro": "Outro marco",
    }[event_type]


def _clean_strings(values: list[str]) -> list[str]:
    return _unique_strings([value.strip() for value in values if value.strip()])


def _is_meaningful_excerpt(value: str) -> bool:
    words = re.findall(r"[A-Za-zÀ-ÿ0-9]+", value)
    return len(value.strip()) >= MIN_EXCERPT_CHARS and len(words) >= MIN_EXCERPT_WORDS


def _event_field_for_gap(value: str) -> str | None:
    normalized = _fold_identifier(value)
    aliases = {
        "data_fato": ("datafato", "horariofato", "localfato"),
        "nascimento_reu": ("nascimentoreu", "datadenascimentodoreu"),
        "recebimento_denuncia": (
            "recebimentodenuncia",
            "datadorecebimentodadenuncia",
        ),
        "suspensao_processo": (
            "suspensaoprocesso",
            "suspensaoinicio",
            "suspensaofim",
            "periododesuspensao",
        ),
        "prisao": ("prisao", "flagrante"),
        "liberdade": ("liberdade", "soltura", "medidacautelar"),
        "audiencia": ("audiencia",),
    }
    for field, values in aliases.items():
        if any(alias in normalized for alias in values):
            return field
    return None


def _event_type_supported(
    event_type: str,
    sources: list[SearchResult],
) -> bool:
    required_terms = {
        "data_fato": ("dos fatos", "fato ocorreu", "consta do incluso inquerito"),
        "nascimento_reu": ("nascid", "data de nascimento"),
        "recebimento_denuncia": ("recebo a denuncia", "recebimento da denuncia"),
        "suspensao_inicio": ("suspens", "artigo 366", "art. 366"),
        "suspensao_fim": ("suspens", "artigo 366", "art. 366"),
        "prisao": ("prisao", "preso"),
        "liberdade": ("liberdade", "soltura", "cautelar"),
        "audiencia": ("audiencia",),
    }
    terms = required_terms.get(event_type)
    if terms is None:
        return True
    folded_sources = [_fold_for_search(source.text) for source in sources]
    return any(term in text for text in folded_sources for term in terms)


def _fold_for_search(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(
        character for character in normalized if not unicodedata.combining(character)
    )


def _fold_choice(value: str) -> str:
    return _fold_for_search(value).strip().replace(" ", "_")


def _fold_identifier(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(
        character
        for character in normalized
        if not unicodedata.combining(character) and character.isalnum()
    )


def _ceiling_division(value: int, divisor: int) -> int:
    return (value + divisor - 1) // divisor


def _unique_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _delay_before_remaining_section(
    repository: HearingDossierRepository,
    processo_id: str,
    current_section: str,
    delay_seconds: float,
) -> None:
    if delay_seconds <= 0:
        return
    current_index = DOSSIER_SECTION_KEYS.index(current_section)
    remaining_keys = set(DOSSIER_SECTION_KEYS[current_index + 1 :])
    if not remaining_keys:
        return
    dossier = repository.get(processo_id)
    if dossier is None:
        return
    if any(
        section.key in remaining_keys and section.status != "concluido"
        for section in dossier.sections
    ):
        time.sleep(delay_seconds)
