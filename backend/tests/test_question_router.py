from preparador_audiencia.question_router import rank_question_guides, route_question


def test_route_question_ranks_custody_guides() -> None:
    route = route_question("O que perguntar na audiencia de custodia sobre a prisao?")

    assert route.area == "criminal"
    assert route.audiencia == "custodia"
    assert route.guides
    assert "custodia" in route.guides[0].tags


def test_route_question_builds_internal_prompt_without_replacing_original_question() -> None:
    pergunta = "A prisao preventiva ainda e necessaria diante das provas?"

    route = route_question(pergunta)
    llm_question = route.llm_question()

    assert pergunta in llm_question
    assert "Triagem interna" in llm_question
    assert "Perguntas-guia ranqueadas" in llm_question


def test_route_question_does_not_enrich_search_with_weak_generic_match() -> None:
    pergunta = "Quando foi a audiencia?"

    route = route_question(pergunta)

    assert route.guides == []
    assert route.area is None
    assert route.audiencia is None
    assert route.search_query() == pergunta
    assert route.guide_query() == ""
    assert route.llm_question() == pergunta


def test_route_question_recognizes_judgment_result_intent() -> None:
    pergunta = "Qual foi o resultado do recurso e quando ocorreu o julgamento?"

    route = route_question(pergunta)

    assert route.guides
    assert route.guides[0].id == "geral_resultado_julgamento"
    assert "provimento" in route.search_query()
    assert "orgao julgador" in route.search_query()


def test_rank_question_guides_removes_repeated_candidate_topics() -> None:
    guides = rank_question_guides("Qual foi o resultado do habeas corpus?")
    topics = [guide.titulo.split(" - ", 1)[0] for guide in guides]

    assert len(topics) == len(set(topics))


def test_rank_question_guides_ignores_empty_question() -> None:
    assert rank_question_guides("   ") == []


def test_route_question_ignores_generic_word_aparece() -> None:
    route = route_question(
        "O que o processo informa sobre mandado e audiencia e em qual contexto isso aparece?"
    )

    assert "saude_condicao_tratamento" not in [guide.id for guide in route.guides]


def test_route_question_requires_result_intent_for_judgment_guide() -> None:
    pergunta = (
        "Qual e o recurso, quem foi o relator e qual tema familiar aparece no julgamento?"
    )
    route = route_question(pergunta)

    guide_ids = [guide.id for guide in route.guides]

    assert "geral_resultado_julgamento" not in guide_ids
    assert guide_ids[0] == "geral_identificacao_julgamento"
    assert "numero" in route.search_query()
    assert "relator" in route.search_query()
    assert pergunta not in route.guide_query()


def test_route_question_rejects_single_weak_overlap_in_multi_topic_question() -> None:
    route = route_question(
        "O que o processo informa sobre criminal e julgamento e em qual contexto isso aparece?"
    )

    assert route.guides == []
