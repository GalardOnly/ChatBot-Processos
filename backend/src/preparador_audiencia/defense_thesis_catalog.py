from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_CATALOG_PATH = (
    Path(__file__).resolve().parents[2] / "data/legal_rules/defense_theses.json"
)


@dataclass(frozen=True)
class DefenseLegalSource:
    id: str
    authority: str
    title: str
    reference: str
    url: str


@dataclass(frozen=True)
class DefenseThesisDefinition:
    id: str
    title: str
    category: str
    question: str
    legal_source_ids: tuple[str, ...]


@dataclass(frozen=True)
class DefenseThesisCatalog:
    id: str
    version: str
    verified_at: str
    scope: str
    search_queries: tuple[str, ...]
    sources: tuple[DefenseLegalSource, ...]
    theses: tuple[DefenseThesisDefinition, ...]


def load_defense_thesis_catalog(
    path: str | Path | None = None,
) -> DefenseThesisCatalog:
    resolved_path = Path(path) if path is not None else DEFAULT_CATALOG_PATH
    payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("Schema do catalogo de teses defensivas nao suportado.")
    raw = payload["catalog"]
    catalog = DefenseThesisCatalog(
        id=str(raw["id"]),
        version=str(raw["version"]),
        verified_at=str(raw["verified_at"]),
        scope=str(raw["scope"]),
        search_queries=tuple(str(item) for item in raw["search_queries"]),
        sources=tuple(
            DefenseLegalSource(
                id=str(item["id"]),
                authority=str(item["authority"]),
                title=str(item["title"]),
                reference=str(item["reference"]),
                url=str(item["url"]),
            )
            for item in raw["sources"]
        ),
        theses=tuple(
            DefenseThesisDefinition(
                id=str(item["id"]),
                title=str(item["title"]),
                category=str(item["category"]),
                question=str(item["question"]),
                legal_source_ids=tuple(str(value) for value in item["legal_source_ids"]),
            )
            for item in raw["theses"]
        ),
    )
    _validate_catalog(catalog)
    return catalog


def _validate_catalog(catalog: DefenseThesisCatalog) -> None:
    if catalog.id != "teses_defensivas_criminais":
        raise ValueError("Identificador do catalogo de teses defensivas invalido.")
    date.fromisoformat(catalog.verified_at)
    if not catalog.search_queries or not catalog.theses:
        raise ValueError("O catalogo precisa de consultas e teses.")
    source_ids = [source.id for source in catalog.sources]
    thesis_ids = [thesis.id for thesis in catalog.theses]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("O catalogo contem fontes juridicas duplicadas.")
    if len(thesis_ids) != len(set(thesis_ids)):
        raise ValueError("O catalogo contem teses duplicadas.")
    known_sources = set(source_ids)
    for source in catalog.sources:
        if not _is_official_url(source.url):
            raise ValueError(f"Fonte juridica nao oficial: {source.url}")
    for thesis in catalog.theses:
        unknown = set(thesis.legal_source_ids) - known_sources
        if unknown:
            raise ValueError(
                f"Tese {thesis.id} referencia fontes desconhecidas: "
                f"{', '.join(sorted(unknown))}"
            )


def _is_official_url(url: str) -> bool:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (
        hostname == "planalto.gov.br" or hostname.endswith(".planalto.gov.br")
    )
