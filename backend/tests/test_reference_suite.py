import json

import pytest

from preparador_audiencia.reference_suite import (
    ReferenceCase,
    ReferenceProcess,
    ReferenceSuite,
    load_reference_suite,
    write_reference_suite,
)


def _case(**overrides: object) -> ReferenceCase:
    values = {
        "id": "prisao-preventiva",
        "pergunta": "Quais fundamentos sustentam a prisao preventiva?",
        "expected_pages": [3, 8],
        "expected_terms": ["garantia da ordem publica", "prisao preventiva"],
        "response_relevant_pages": [3, 8, 12],
        "response_expected_terms": [
            "garantia da ordem publica || ordem publica",
            "prisao preventiva",
        ],
        "review_status": "approved",
        "reviewer": "Defensor revisor",
        "review_notes": "Conferido diretamente no processo.",
    }
    values.update(overrides)
    return ReferenceCase(**values)


def _process(**overrides: object) -> ReferenceProcess:
    values = {
        "id": "processo-hc-001",
        "domain": "penal.prisao-cautelar",
        "document": "hc-publico.pdf",
        "source": "HC publico anonimizado",
        "source_url": "https://example.test/hc-publico.pdf",
        "sha256": "a" * 64,
        "text_sha256": "b" * 64,
        "cases": [_case()],
    }
    values.update(overrides)
    return ReferenceProcess(**values)


def _suite(**overrides: object) -> ReferenceSuite:
    values = {
        "id": "referencia-penal-v1",
        "description": "Casos revisados para avaliar respostas sobre prisao cautelar.",
        "processes": [_process()],
    }
    values.update(overrides)
    return ReferenceSuite(**values)


def test_write_and_load_reference_suite_round_trip(tmp_path) -> None:
    suite = _suite()
    output = tmp_path / "nested" / "reference-suite.json"

    write_reference_suite(suite, output)
    loaded = load_reference_suite(output)

    assert loaded == suite
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert payload["processes"][0]["cases"][0]["review_status"] == "approved"
    assert output.read_text(encoding="utf-8").endswith("\n")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("id", "Caso Invalido", "caso.id"),
        ("pergunta", "   ", "pergunta deve ser texto nao vazio"),
        ("expected_pages", [], "expected_pages deve ser uma lista nao vazia"),
        ("expected_pages", [0], "inteiros positivos"),
        ("expected_pages", [3, 2], "ordem crescente"),
        ("expected_pages", [2, 2], "sem duplicatas"),
        (
            "response_relevant_pages",
            [8, 3],
            "response_relevant_pages deve estar em ordem crescente",
        ),
        ("expected_terms", [], "expected_terms deve ser uma lista nao vazia"),
        ("expected_terms", ["prisao", "  "], "textos nao vazios"),
        ("expected_terms", ["Prisao", "prisao"], "nao pode conter duplicatas"),
        (
            "response_expected_terms",
            ["resposta", "  "],
            "response_expected_terms deve conter apenas textos nao vazios",
        ),
        ("review_status", "done", "review_status invalido"),
    ],
)
def test_reference_case_rejects_invalid_values(
    field: str,
    value: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _case(**{field: value})


@pytest.mark.parametrize("status", ["in_review", "approved", "rejected"])
def test_reviewed_status_requires_reviewer(status: str) -> None:
    with pytest.raises(ValueError, match="reviewer e obrigatorio"):
        _case(review_status=status, reviewer=None)


def test_pending_status_rejects_reviewer() -> None:
    with pytest.raises(ValueError, match="reviewer deve ser nulo"):
        _case(review_status="pending", reviewer="Pessoa revisora")


def test_process_validates_domain_and_duplicate_case_ids() -> None:
    with pytest.raises(ValueError, match="processo.domain"):
        _process(domain="Direito Penal")

    with pytest.raises(ValueError, match="caso.id duplicado"):
        _process(cases=[_case(), _case()])


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("document", "../segredo.pdf", "nome de um arquivo PDF"),
        ("document", "processo.txt", "nome de um arquivo PDF"),
        ("source_url", "", "source_url"),
        ("sha256", "abc", "hash hexadecimal"),
        ("text_sha256", "abc", "hash hexadecimal"),
    ],
)
def test_process_rejects_invalid_document_metadata(
    field: str,
    value: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _process(**{field: value})


def test_suite_validates_version_and_duplicate_process_ids() -> None:
    with pytest.raises(ValueError, match="schema_version deve ser"):
        _suite(schema_version="2.0")

    with pytest.raises(ValueError, match="processo.id duplicado"):
        _suite(processes=[_process(), _process()])


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"pergunta": 123}, "caso.pergunta deve ser texto"),
        ({"expected_pages": [True]}, "caso.expected_pages deve conter apenas inteiros"),
        ({"expected_terms": ["prisao", 7]}, "caso.expected_terms deve conter apenas textos"),
        ({"campo_errado": "valor"}, "campos desconhecidos"),
    ],
)
def test_load_rejects_invalid_case_json(tmp_path, change, message) -> None:
    payload = _suite().to_dict()
    payload["processes"][0]["cases"][0].update(change)
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_reference_suite(path)


def test_load_rejects_non_object_root(tmp_path) -> None:
    path = tmp_path / "invalid-root.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="raiz deve ser um objeto JSON"):
        load_reference_suite(path)


def test_write_revalidates_mutable_nested_data(tmp_path) -> None:
    suite = _suite()
    suite.processes[0].cases[0].expected_pages.append(-1)

    with pytest.raises(ValueError, match="inteiros positivos"):
        write_reference_suite(suite, tmp_path / "suite.json")


def test_write_requires_reference_suite(tmp_path) -> None:
    with pytest.raises(TypeError, match="suite deve ser uma ReferenceSuite"):
        write_reference_suite({"id": "invalida"}, tmp_path / "suite.json")
