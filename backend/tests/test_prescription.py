from datetime import date

import pytest

from preparador_audiencia.prescription import (
    InterruptiveMilestone,
    InvalidPrescriptionInput,
    OffensePrescriptionInput,
    PrescriptionCalculationInput,
    SuspensionPeriod,
    calculate_prescription,
    prescription_period_months,
)


def _offense(**overrides) -> OffensePrescriptionInput:
    values = {
        "offense_id": "delito-1",
        "description": "Furto",
        "article": "Art. 155 do CP",
        "maximum_penalty_months": 48,
        "initial_term_type": "consumacao",
        "initial_term_date": date(2020, 1, 10),
        "fact_date": date(2020, 1, 10),
        "sexual_violence_against_woman": False,
        "interruptive_milestones": (),
        "suspension_periods": (),
    }
    values.update(overrides)
    return OffensePrescriptionInput(**values)


def _calculation(*offenses, **overrides) -> PrescriptionCalculationInput:
    values = {
        "reference_date": date(2026, 8, 3),
        "defendant_name": "Pessoa testada",
        "defendant_birth_date": date(1990, 1, 1),
        "sentence_status": "nao_proferida",
        "conviction_sentence_date": None,
        "offenses": tuple(offenses or (_offense(),)),
    }
    values.update(overrides)
    return PrescriptionCalculationInput(**values)


@pytest.mark.parametrize(
    ("maximum_months", "expected_period"),
    [
        (11, 36),
        (12, 48),
        (24, 48),
        (25, 96),
        (48, 96),
        (49, 144),
        (96, 144),
        (97, 192),
        (144, 192),
        (145, 240),
    ],
)
def test_article_109_thresholds(maximum_months: int, expected_period: int) -> None:
    assert prescription_period_months(maximum_months) == expected_period


def test_article_10_includes_initial_day_and_deadline_is_previous_anniversary_day() -> None:
    result = calculate_prescription(
        _calculation(
            _offense(maximum_penalty_months=11),
            reference_date=date(2023, 1, 9),
        )
    ).offenses[0]

    assert result.final_deadline == date(2023, 1, 9)
    assert result.status == "vence_na_data_referencia"


def test_interruptive_event_on_deadline_resets_the_period() -> None:
    offense = _offense(
        maximum_penalty_months=11,
        interruptive_milestones=(
            InterruptiveMilestone("recebimento_denuncia", date(2023, 1, 9)),
        ),
    )
    result = calculate_prescription(
        _calculation(offense, reference_date=date(2024, 1, 1))
    ).offenses[0]

    assert result.intervals[0].status == "interrompido_em_tempo"
    assert result.final_deadline == date(2026, 1, 8)
    assert result.status == "prazo_nao_esgotado_no_calculo"


def test_interval_does_not_include_suspension_that_happened_after_its_event() -> None:
    offense = _offense(
        interruptive_milestones=(
            InterruptiveMilestone("recebimento_denuncia", date(2021, 1, 10)),
        ),
        suspension_periods=(
            SuspensionPeriod("art_116", date(2022, 1, 1), date(2023, 1, 1)),
        ),
    )
    result = calculate_prescription(_calculation(offense)).offenses[0]

    assert result.intervals[0].suspended_days == 0
    assert result.intervals[0].deadline == date(2028, 1, 9)
    assert result.intervals[1].suspended_days == 365


def test_late_event_does_not_revive_elapsed_period() -> None:
    offense = _offense(
        maximum_penalty_months=11,
        interruptive_milestones=(
            InterruptiveMilestone("recebimento_denuncia", date(2023, 1, 10)),
        ),
    )
    result = calculate_prescription(
        _calculation(offense, reference_date=date(2024, 1, 1))
    ).offenses[0]

    assert result.status == "prazo_esgotado_no_calculo"
    assert result.final_deadline == date(2023, 1, 9)
    assert result.intervals[0].status == "prazo_esgotado_antes_do_marco"


def test_closed_suspension_extends_deadline() -> None:
    offense = _offense(
        maximum_penalty_months=11,
        suspension_periods=(
            SuspensionPeriod("art_116", date(2021, 1, 1), date(2021, 1, 31)),
        ),
    )
    result = calculate_prescription(
        _calculation(offense, reference_date=date(2023, 2, 1))
    ).offenses[0]

    assert result.final_deadline == date(2023, 2, 8)
    assert result.intervals[0].suspended_days == 30
    assert result.status == "prazo_nao_esgotado_no_calculo"


def test_overlapping_suspensions_are_counted_once() -> None:
    offense = _offense(
        maximum_penalty_months=11,
        suspension_periods=(
            SuspensionPeriod("art_116", date(2021, 1, 1), date(2021, 1, 31)),
            SuspensionPeriod("outra_legal", date(2021, 1, 20), date(2021, 2, 10)),
        ),
    )
    result = calculate_prescription(_calculation(offense)).offenses[0]

    assert result.intervals[0].suspended_days == 40


def test_open_suspension_makes_result_inconclusive() -> None:
    offense = _offense(
        suspension_periods=(SuspensionPeriod("cpp_366", date(2024, 1, 1), None),)
    )
    result = calculate_prescription(_calculation(offense)).offenses[0]

    assert result.status == "inconclusivo"
    assert "Sumula 415" in result.warnings[0]


def test_under_21_at_fact_halves_period() -> None:
    result = calculate_prescription(
        _calculation(
            _offense(maximum_penalty_months=48),
            defendant_birth_date=date(2000, 2, 1),
        )
    ).offenses[0]

    assert result.base_period_months == 96
    assert result.applied_period_months == 48
    assert result.article_115_reduction_applied is True


def test_exactly_21_at_fact_does_not_halve_period() -> None:
    result = calculate_prescription(
        _calculation(
            _offense(maximum_penalty_months=48),
            defendant_birth_date=date(1999, 1, 10),
        )
    ).offenses[0]

    assert result.applied_period_months == 96
    assert result.article_115_reduction_applied is False


def test_over_70_at_sentence_halves_period() -> None:
    result = calculate_prescription(
        _calculation(
            _offense(
                maximum_penalty_months=48,
                interruptive_milestones=(
                    InterruptiveMilestone(
                        "sentenca_condenatoria_recorrivel",
                        date(2020, 2, 1),
                    ),
                ),
            ),
            defendant_birth_date=date(1940, 1, 1),
            sentence_status="proferida",
            conviction_sentence_date=date(2020, 2, 1),
        )
    ).offenses[0]

    assert "reu_maior_de_70_na_data_da_sentenca" in result.article_115_reasons
    assert result.applied_period_months == 48


def test_exactly_70_at_sentence_does_not_halve_period() -> None:
    result = calculate_prescription(
        _calculation(
            _offense(
                maximum_penalty_months=48,
                interruptive_milestones=(
                    InterruptiveMilestone(
                        "sentenca_condenatoria_recorrivel",
                        date(2020, 2, 1),
                    ),
                ),
            ),
            defendant_birth_date=date(1950, 2, 1),
            sentence_status="proferida",
            conviction_sentence_date=date(2020, 2, 1),
        )
    ).offenses[0]

    assert result.applied_period_months == 96
    assert result.article_115_reduction_applied is False


def test_2025_sexual_violence_exception_prevents_reduction() -> None:
    offense = _offense(
        initial_term_date=date(2025, 7, 4),
        fact_date=date(2025, 7, 4),
        sexual_violence_against_woman=True,
    )
    result = calculate_prescription(
        _calculation(offense, defendant_birth_date=date(2006, 1, 1))
    ).offenses[0]

    assert result.article_115_reduction_applied is False
    assert result.applied_period_months == result.base_period_months


def test_2025_exception_is_not_applied_retroactively() -> None:
    offense = _offense(
        fact_date=date(2025, 7, 3),
        initial_term_date=date(2025, 7, 3),
        sexual_violence_against_woman=True,
    )
    result = calculate_prescription(
        _calculation(offense, defendant_birth_date=date(2006, 1, 1))
    ).offenses[0]

    assert result.article_115_reduction_applied is True


def test_unknown_2025_sexual_violence_flag_blocks_age_reduction() -> None:
    offense = _offense(
        fact_date=date(2025, 7, 4),
        initial_term_date=date(2025, 7, 4),
        sexual_violence_against_woman=None,
    )
    result = calculate_prescription(
        _calculation(offense, defendant_birth_date=date(2006, 1, 1))
    ).offenses[0]

    assert result.status == "inconclusivo"
    assert "violencia sexual" in result.missing_fields[0]


def test_missing_birth_date_blocks_categorical_result() -> None:
    result = calculate_prescription(
        _calculation(_offense(), defendant_birth_date=None)
    ).offenses[0]

    assert result.status == "inconclusivo"
    assert "nascimento" in result.missing_fields[0]


def test_conviction_without_interruptive_publication_is_inconclusive() -> None:
    result = calculate_prescription(
        _calculation(
            _offense(),
            sentence_status="proferida",
            conviction_sentence_date=date(2020, 2, 1),
        )
    ).offenses[0]

    assert result.status == "inconclusivo"
    assert "publicacao" in result.missing_fields[0]


def test_multiple_offenses_are_calculated_independently() -> None:
    result = calculate_prescription(
        _calculation(
            _offense(offense_id="curto", maximum_penalty_months=11),
            _offense(offense_id="longo", maximum_penalty_months=145),
            reference_date=date(2024, 1, 1),
        )
    )

    by_id = {item.offense_id: item for item in result.offenses}
    assert by_id["curto"].status == "prazo_esgotado_no_calculo"
    assert by_id["longo"].status == "prazo_nao_esgotado_no_calculo"


def test_rejects_interruptive_event_inside_suspension() -> None:
    offense = _offense(
        interruptive_milestones=(
            InterruptiveMilestone("recebimento_denuncia", date(2021, 1, 10)),
        ),
        suspension_periods=(
            SuspensionPeriod("art_116", date(2021, 1, 1), date(2021, 2, 1)),
        ),
    )

    with pytest.raises(InvalidPrescriptionInput, match="dentro de suspensao"):
        calculate_prescription(_calculation(offense))


def test_rejects_duplicate_offense_ids() -> None:
    with pytest.raises(InvalidPrescriptionInput, match="devem ser unicos"):
        calculate_prescription(
            _calculation(
                _offense(offense_id="repetido"),
                _offense(offense_id="repetido"),
            )
        )
