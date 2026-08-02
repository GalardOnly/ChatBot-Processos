from preparador_audiencia.prompts.criminal_analysis import (
    CRIMINAL_ANALYSIS_SECTIONS,
)


def _section(key: str):
    return next(section for section in CRIMINAL_ANALYSIS_SECTIONS if section.key == key)


def test_criminal_analysis_sections_have_unique_keys_and_grounding_rules() -> None:
    keys = [section.key for section in CRIMINAL_ANALYSIS_SECTIONS]

    assert len(keys) == 5
    assert len(keys) == len(set(keys))
    assert all(section.top_k <= 20 for section in CRIMINAL_ANALYSIS_SECTIONS)
    for section in CRIMINAL_ANALYSIS_SECTIONS:
        assert "[p. N]" in section.prompt
        assert "Nao localizado no processo" in section.prompt
        assert "nao complete lacunas" in section.prompt


def test_prescription_timeline_keeps_required_dates_together_without_calculating() -> None:
    prompt = _section("linha_prescricao").prompt

    required_fields = (
        "data, horario e local do fato",
        "data de nascimento do reu",
        "data do recebimento da denuncia ou queixa",
        "suspensoes do processo",
        "artigo citado",
        "pena maxima",
    )
    assert all(field in prompt for field in required_fields)
    assert "Nao calcule prazo" in prompt
    assert "nao declare prescricao" in prompt


def test_testimony_section_does_not_promise_integral_or_visual_analysis() -> None:
    prompt = _section("depoimentos_provas").prompt

    assert "transcreva literalmente apenas os trechos recuperados" in prompt
    assert "marque como parcial" in prompt
    assert "Nao interprete por conta propria o conteudo visual" in prompt


def test_contact_section_requests_chronology_and_does_not_claim_current_data() -> None:
    prompt = _section("identificacao_contatos").prompt

    assert "enderecos e telefones em ordem cronologica" in prompt
    assert "registro mais recente" in prompt
    assert "sem afirmar que ainda e atual" in prompt
