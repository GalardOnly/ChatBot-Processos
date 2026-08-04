import json
from pathlib import Path

import pytest

from preparador_audiencia.defense_thesis_catalog import (
    load_defense_thesis_catalog,
)


def test_loads_versioned_catalog_with_official_sources() -> None:
    catalog = load_defense_thesis_catalog()

    assert catalog.version == "1.0.0"
    assert len(catalog.theses) == 13
    assert {item.id for item in catalog.theses} >= {
        "duvida_autoria",
        "falta_materialidade",
        "dosimetria_favoravel",
        "prescricao",
    }
    assert all("planalto.gov.br" in source.url for source in catalog.sources)


def test_rejects_non_official_legal_source(tmp_path) -> None:
    source_path = tmp_path / "catalog.json"
    original = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "data/legal_rules/defense_theses.json"
        ).read_text(encoding="utf-8")
    )
    original["catalog"]["sources"][0]["url"] = "https://example.com/resumo"
    source_path.write_text(json.dumps(original), encoding="utf-8")

    with pytest.raises(ValueError, match="nao oficial"):
        load_defense_thesis_catalog(source_path)
