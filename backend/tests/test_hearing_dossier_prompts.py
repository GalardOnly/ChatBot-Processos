from preparador_audiencia.prompts.hearing_dossier import (
    MAX_PRIOR_CONTEXT_CHARS,
    MAX_TOTAL_SOURCE_CHARS,
    build_section_prompts,
)
from preparador_audiencia.search import SearchResult


def test_dossier_prompt_compacts_large_chunks_around_relevant_terms() -> None:
    large_text = "inicio " + ("x" * 2_000) + " data de nascimento 10/01/1990 " + (
        "y" * 2_000
    )
    sources = [
        SearchResult(
            text=large_text,
            page_number=index,
            chunk_index=0,
            document_type=None,
            score=0.9,
        )
        for index in range(1, 19)
    ]
    prior = {"depoimentos": {"texto": "z" * 10_000}}

    _, user_prompt = build_section_prompts("marcos_essenciais", sources, prior)

    assert "data de nascimento 10/01/1990" in user_prompt
    assert len(user_prompt) < (
        MAX_TOTAL_SOURCE_CHARS + MAX_PRIOR_CONTEXT_CHARS + 5_000
    )
    assert "contexto posterior omitido" in user_prompt
