import json

from preparador_audiencia.question_sources import (
    generate_question_candidates,
    load_question_sources,
    question_candidates_to_cases,
    render_question_candidates_markdown,
    write_question_candidates,
)


def test_load_question_sources_reads_curated_file() -> None:
    sources = load_question_sources()

    assert len(sources) >= 10
    assert any(source.id == "mpmg-manual-custodia" for source in sources)
    assert any(source.kind == "dataset" for source in sources)


def test_generate_question_candidates_reaches_initial_scale() -> None:
    candidates = generate_question_candidates(load_question_sources())

    assert len(candidates) >= 150
    assert all(candidate.status == "candidate" for candidate in candidates)
    assert all(candidate.source_url.startswith("http") for candidate in candidates)


def test_generate_question_candidates_filters_official_custody_questions() -> None:
    candidates = generate_question_candidates(
        load_question_sources(),
        area="criminal",
        audiencia="custodia",
        official_only=True,
    )

    assert candidates
    assert all(candidate.area == "criminal" for candidate in candidates)
    assert all(candidate.audiencia == "custodia" for candidate in candidates)
    assert all(candidate.official_source for candidate in candidates)


def test_question_candidates_to_cases_can_feed_benchmark() -> None:
    candidates = generate_question_candidates(load_question_sources(), area="familia", limit=2)

    payload = question_candidates_to_cases(candidates)

    assert payload["source_id"] == "perguntas-candidatas-curadas-v0.1"
    assert len(payload["cases"]) == 2
    assert payload["cases"][0]["expected_pages"] == []


def test_render_question_candidates_markdown_mentions_review_status() -> None:
    candidates = generate_question_candidates(load_question_sources(), area="geral", limit=1)

    markdown = render_question_candidates_markdown(candidates)

    assert "Perguntas Candidatas para Audiencia" in markdown
    assert "candidate" in markdown
    assert candidates[0].source_title in markdown


def test_write_question_candidates_json(tmp_path) -> None:
    output = tmp_path / "candidates.json"
    candidates = generate_question_candidates(load_question_sources(), limit=1)

    write_question_candidates(candidates, output, output_format="json")

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload[0]["id"] == candidates[0].id
