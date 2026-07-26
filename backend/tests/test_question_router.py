from preparador_audiencia.question_router import rank_question_guides, route_question


def test_route_question_ranks_custody_guides() -> None:
    route = route_question("O que perguntar na audiencia de custodia sobre a prisao?")

    assert route.area == "criminal"
    assert route.audiencia == "custodia"
    assert route.guides
    assert "custodia" in route.guides[0].tags


def test_route_question_builds_internal_prompt_without_replacing_original_question() -> None:
    pergunta = "Quais pontos eu deveria confirmar antes da audiencia?"

    route = route_question(pergunta)
    llm_question = route.llm_question()

    assert pergunta in llm_question
    assert "Triagem interna" in llm_question
    assert "Perguntas-guia ranqueadas" in llm_question


def test_rank_question_guides_ignores_empty_question() -> None:
    assert rank_question_guides("   ") == []
