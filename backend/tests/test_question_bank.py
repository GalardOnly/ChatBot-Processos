import json

from preparador_audiencia.question_bank import (
    list_question_templates,
    question_templates_to_cases,
    render_question_templates_markdown,
    write_question_templates,
)


def test_list_question_templates_filters_by_area_and_tag() -> None:
    templates = list_question_templates(area="criminal", tags=["custodia"])

    assert templates
    assert all(template.area == "criminal" for template in templates)
    assert all("custodia" in template.tags for template in templates)


def test_question_templates_to_cases_can_feed_response_benchmark() -> None:
    templates = list_question_templates(area="geral", limit=2)

    payload = question_templates_to_cases(templates)

    assert payload["source_id"] == "banco-perguntas-audiencia-v0.1"
    assert len(payload["cases"]) == 2
    assert payload["cases"][0]["expected_pages"] == []
    assert payload["cases"][0]["expected_terms"] == []


def test_render_question_templates_markdown_includes_prompt() -> None:
    templates = list_question_templates(area="familia", limit=1)

    markdown = render_question_templates_markdown(templates)

    assert "Banco de Perguntas para Audiencia" in markdown
    assert templates[0].pergunta in markdown


def test_write_question_templates_cases_json(tmp_path) -> None:
    output = tmp_path / "cases.json"
    templates = list_question_templates(area="geral", limit=1)

    write_question_templates(templates, output, output_format="cases-json")

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["cases"][0]["id"] == templates[0].id
