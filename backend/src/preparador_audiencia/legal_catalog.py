from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_LEGAL_RULES_DIR = Path(__file__).resolve().parents[2] / "data/legal_rules"
ALLOWED_OFFICIAL_DOMAINS = ("cnj.jus.br", "planalto.gov.br", "stj.jus.br")


@dataclass(frozen=True)
class LegalSource:
    id: str
    authority: str
    kind: str
    title: str
    reference: str
    url: str
    summary: str


@dataclass(frozen=True)
class LegalRequirement:
    id: str
    category: str
    label: str
    question: str
    condition: str
    legal_source_ids: tuple[str, ...]


@dataclass(frozen=True)
class LegalTopic:
    id: str
    title: str
    version: str
    verified_at: str
    scope: str
    search_queries: tuple[str, ...]
    sources: tuple[LegalSource, ...]
    requirements: tuple[LegalRequirement, ...]


def load_legal_topic(
    topic_id: str,
    rules_dir: str | Path | None = None,
) -> LegalTopic:
    directory = Path(rules_dir) if rules_dir is not None else DEFAULT_LEGAL_RULES_DIR
    path = directory / _topic_filename(topic_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError(f"Schema juridico nao suportado em {path.name}.")

    raw_topic = payload["topic"]
    topic = LegalTopic(
        id=str(raw_topic["id"]),
        title=str(raw_topic["title"]),
        version=str(raw_topic["version"]),
        verified_at=str(raw_topic["verified_at"]),
        scope=str(raw_topic["scope"]),
        search_queries=tuple(str(query) for query in raw_topic["search_queries"]),
        sources=tuple(_source_from_dict(item) for item in raw_topic["sources"]),
        requirements=tuple(
            _requirement_from_dict(item) for item in raw_topic["requirements"]
        ),
    )
    _validate_topic(topic, expected_id=topic_id)
    return topic


def _topic_filename(topic_id: str) -> str:
    filenames = {"reconhecimento_pessoas": "recognition_person.json"}
    try:
        return filenames[topic_id]
    except KeyError as exc:
        raise ValueError(f"Tema juridico desconhecido: {topic_id}") from exc


def _source_from_dict(item: dict[str, object]) -> LegalSource:
    return LegalSource(
        id=str(item["id"]),
        authority=str(item["authority"]),
        kind=str(item["kind"]),
        title=str(item["title"]),
        reference=str(item["reference"]),
        url=str(item["url"]),
        summary=str(item["summary"]),
    )


def _requirement_from_dict(item: dict[str, object]) -> LegalRequirement:
    return LegalRequirement(
        id=str(item["id"]),
        category=str(item["category"]),
        label=str(item["label"]),
        question=str(item["question"]),
        condition=str(item["condition"]),
        legal_source_ids=tuple(str(source_id) for source_id in item["legal_source_ids"]),
    )


def _validate_topic(topic: LegalTopic, *, expected_id: str) -> None:
    if topic.id != expected_id:
        raise ValueError(f"Tema juridico divergente: esperado {expected_id}, recebido {topic.id}.")
    date.fromisoformat(topic.verified_at)
    if not topic.search_queries:
        raise ValueError("O tema juridico precisa de consultas de recuperacao.")

    source_ids = [source.id for source in topic.sources]
    requirement_ids = [requirement.id for requirement in topic.requirements]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("O catalogo juridico contem fontes duplicadas.")
    if len(requirement_ids) != len(set(requirement_ids)):
        raise ValueError("O catalogo juridico contem requisitos duplicados.")

    known_source_ids = set(source_ids)
    for source in topic.sources:
        if not _is_official_url(source.url):
            raise ValueError(f"Fonte juridica nao oficial: {source.url}")
    for requirement in topic.requirements:
        if requirement.category not in {"aplicabilidade", "validade", "impacto"}:
            raise ValueError(f"Categoria juridica invalida: {requirement.category}")
        unknown_ids = set(requirement.legal_source_ids) - known_source_ids
        if unknown_ids:
            raise ValueError(
                f"Requisito {requirement.id} referencia fontes desconhecidas: "
                f"{', '.join(sorted(unknown_ids))}"
            )


def _is_official_url(url: str) -> bool:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in ALLOWED_OFFICIAL_DOMAINS
    )
