from preparador_audiencia.testimony_identification import (
    identify_testimony_person,
    normalize_person_name,
)


def test_identifies_explicit_witness_label_with_high_confidence() -> None:
    result = identify_testimony_person(
        [(7, "A TESTEMUNHA: Maria da Conceicao Silva\nINQUERITO 12")],
        "testemunha",
    )

    assert result.name == "Maria da Conceicao Silva"
    assert result.method == "rotulo_cabecalho"
    assert result.confidence == "alta"
    assert result.page_number == 7
    assert result.evidence == "A TESTEMUNHA: Maria da Conceicao Silva"


def test_identifies_nominal_declaration_split_across_lines() -> None:
    result = identify_testimony_person(
        [
            (
                3,
                "TERMO DE\nDECLARACAO DE ANA PAULA DE\nOLIVEIRA\nINQUERITO 9",
            )
        ],
        "declarante",
    )

    assert result.name == "ANA PAULA DE OLIVEIRA"
    assert result.method == "titulo_nominal"
    assert result.confidence == "alta"
    assert result.normalized_name == "ANA PAULA DE OLIVEIRA"


def test_marks_indirect_qualification_with_medium_confidence() -> None:
    result = identify_testimony_person(
        [(4, "Compareceu em cartorio Pedro Henrique Lima, nacionalidade brasileira")],
        "declarante",
    )

    assert result.name == "Pedro Henrique Lima"
    assert result.method == "qualificacao"
    assert result.confidence == "media"


def test_does_not_treat_narrative_mention_as_person_identification() -> None:
    result = identify_testimony_person(
        [(22, "A testemunha confirmou os fatos narrados pela vitima.")],
        "testemunha",
    )

    assert result.name is None
    assert result.status == "nao_identificado"
    assert result.method == "nao_identificado"
    assert result.confidence == "baixa"


def test_does_not_treat_generic_role_in_title_as_person_name() -> None:
    result = identify_testimony_person(
        [(8, "TERMO DE DEPOIMENTO DE TESTEMUNHA OCULAR\nINQUERITO 3")],
        "testemunha",
    )

    assert result.name is None


def test_normalizes_person_name_for_future_statement_grouping() -> None:
    assert normalize_person_name("  Nâyara  Falcão Lima ") == "NAYARA FALCAO LIMA"
