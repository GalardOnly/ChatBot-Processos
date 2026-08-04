from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

PRESCRIPTION_CALCULATION_VERSION = "1.0"
LEGAL_RULESET_VERSION = "cp-artigos-10-109-111-115-116-117-119-2025-07-04"
ARTICLE_115_EXCEPTION_EFFECTIVE_DATE = date(2025, 7, 4)

LEGAL_SOURCES = (
    {
        "id": "codigo-penal",
        "title": "Codigo Penal, arts. 10, 109, 111, 115, 116, 117 e 119",
        "url": "https://www.planalto.gov.br/ccivil_03/decreto-lei/del2848compilado.htm",
    },
    {
        "id": "lei-15160-2025",
        "title": "Lei 15.160/2025, alteracao do art. 115 do Codigo Penal",
        "url": "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/lei/l15160.htm",
    },
    {
        "id": "codigo-processo-penal",
        "title": "Codigo de Processo Penal, art. 366",
        "url": "https://www.planalto.gov.br/ccivil_03/decreto-lei/del3689compilado.htm",
    },
    {
        "id": "sumula-stj-415",
        "title": "Sumula 415 do Superior Tribunal de Justica",
        "url": (
            "https://arquivocidadao.stj.jus.br/index.php/sumula-415?"
            "listLimit=100&onlyDirect=1&sort=referenceCode&sortDir=asc"
        ),
    },
)

_INTERRUPTIVE_EVENT_TYPES = {
    "recebimento_denuncia",
    "recebimento_queixa",
    "pronuncia",
    "confirmacao_pronuncia",
    "sentenca_condenatoria_recorrivel",
    "acordao_condenatorio_recorrivel",
}
_INITIAL_TERM_TYPES = {
    "consumacao",
    "fim_tentativa",
    "fim_permanencia",
    "conhecimento_fato",
    "vitima_18_anos",
}
_SUSPENSION_TYPES = {"art_116", "cpp_366", "cpp_368", "outra_legal"}


@dataclass(frozen=True)
class SourceReference:
    page_number: int | None = None
    excerpt: str | None = None


@dataclass(frozen=True)
class InterruptiveMilestone:
    event_type: str
    event_date: date
    source: SourceReference = field(default_factory=SourceReference)


@dataclass(frozen=True)
class SuspensionPeriod:
    suspension_type: str
    start_date: date
    end_date: date | None
    source: SourceReference = field(default_factory=SourceReference)


@dataclass(frozen=True)
class OffensePrescriptionInput:
    offense_id: str
    description: str
    article: str
    maximum_penalty_months: int
    initial_term_type: str
    initial_term_date: date
    fact_date: date
    sexual_violence_against_woman: bool | None = None
    interruptive_milestones: tuple[InterruptiveMilestone, ...] = ()
    suspension_periods: tuple[SuspensionPeriod, ...] = ()


@dataclass(frozen=True)
class PrescriptionCalculationInput:
    reference_date: date
    defendant_name: str | None
    defendant_birth_date: date | None
    sentence_status: str
    conviction_sentence_date: date | None
    offenses: tuple[OffensePrescriptionInput, ...]


@dataclass(frozen=True)
class PrescriptionInterval:
    start_date: date
    deadline: date
    end_date: date
    end_reason: str
    status: str
    suspended_days: int


@dataclass(frozen=True)
class OffensePrescriptionResult:
    offense_id: str
    description: str
    article: str
    status: str
    base_period_months: int
    applied_period_months: int | None
    article_115_reduction_applied: bool
    article_115_reasons: tuple[str, ...]
    final_deadline: date | None
    days_to_deadline: int | None
    intervals: tuple[PrescriptionInterval, ...]
    missing_fields: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class PrescriptionCalculationResult:
    status: str
    calculated_at_date: date
    calculation_version: str
    legal_ruleset_version: str
    offenses: tuple[OffensePrescriptionResult, ...]
    legal_sources: tuple[dict[str, str], ...]
    warnings: tuple[str, ...]


class InvalidPrescriptionInput(ValueError):
    pass


def calculate_prescription(
    calculation: PrescriptionCalculationInput,
) -> PrescriptionCalculationResult:
    _validate_calculation(calculation)
    offense_results = tuple(
        _calculate_offense(calculation, offense) for offense in calculation.offenses
    )
    statuses = {item.status for item in offense_results}
    if "inconclusivo" in statuses:
        overall_status = "inconclusivo"
    elif "prazo_esgotado_no_calculo" in statuses:
        overall_status = "ha_prazo_esgotado_no_calculo"
    elif "vence_na_data_referencia" in statuses:
        overall_status = "ha_prazo_no_limite"
    else:
        overall_status = "prazos_nao_esgotados_no_calculo"
    return PrescriptionCalculationResult(
        status=overall_status,
        calculated_at_date=calculation.reference_date,
        calculation_version=PRESCRIPTION_CALCULATION_VERSION,
        legal_ruleset_version=LEGAL_RULESET_VERSION,
        offenses=offense_results,
        legal_sources=LEGAL_SOURCES,
        warnings=(
            "Calculo restrito a prescricao da pretensao punitiva pela pena maxima "
            "em abstrato informada e confirmada.",
            "Cada delito foi calculado separadamente, conforme o art. 119 do Codigo Penal.",
            "Datas, pena maxima, marcos e suspensoes devem ser conferidos no processo.",
        ),
    )


def prescription_period_months(maximum_penalty_months: int) -> int:
    if maximum_penalty_months <= 0:
        raise InvalidPrescriptionInput("A pena maxima deve ser maior que zero.")
    if maximum_penalty_months > 144:
        return 240
    if maximum_penalty_months > 96:
        return 192
    if maximum_penalty_months > 48:
        return 144
    if maximum_penalty_months > 24:
        return 96
    if maximum_penalty_months >= 12:
        return 48
    return 36


def _calculate_offense(
    calculation: PrescriptionCalculationInput,
    offense: OffensePrescriptionInput,
) -> OffensePrescriptionResult:
    base_period = prescription_period_months(offense.maximum_penalty_months)
    missing_fields, reduction_reasons = _article_115_reduction(calculation, offense)
    warnings: list[str] = []
    if calculation.sentence_status == "proferida" and not any(
        item.event_type
        in {"sentenca_condenatoria_recorrivel", "acordao_condenatorio_recorrivel"}
        for item in offense.interruptive_milestones
    ):
        missing_fields.append(
            "Data de publicacao da sentenca ou acordao condenatorio recorrivel como "
            "marco interruptivo."
        )
    open_suspensions = [item for item in offense.suspension_periods if item.end_date is None]
    if open_suspensions:
        missing_fields.append(
            "Data final de cada periodo de suspensao; suspensao aberta nao e estimada."
        )
        if any(item.suspension_type == "cpp_366" for item in open_suspensions):
            warnings.append(
                "A suspensao do art. 366 do CPP exige conferir o limite da Sumula 415 do STJ."
            )
    if missing_fields:
        return OffensePrescriptionResult(
            offense_id=offense.offense_id,
            description=offense.description,
            article=offense.article,
            status="inconclusivo",
            base_period_months=base_period,
            applied_period_months=None,
            article_115_reduction_applied=False,
            article_115_reasons=(),
            final_deadline=None,
            days_to_deadline=None,
            intervals=(),
            missing_fields=tuple(dict.fromkeys(missing_fields)),
            warnings=tuple(warnings),
        )

    applied_period = base_period // 2 if reduction_reasons else base_period
    closed_suspensions = _merged_suspensions(offense.suspension_periods)
    events = sorted(offense.interruptive_milestones, key=lambda item: item.event_date)
    intervals: list[PrescriptionInterval] = []
    current_start = offense.initial_term_date
    final_status = "prazo_nao_esgotado_no_calculo"
    final_deadline: date | None = None

    for event in events:
        deadline, suspended_days = _deadline_with_suspensions(
            current_start,
            applied_period,
            closed_suspensions,
            event.event_date,
        )
        if event.event_date > deadline:
            intervals.append(
                PrescriptionInterval(
                    start_date=current_start,
                    deadline=deadline,
                    end_date=event.event_date,
                    end_reason=event.event_type,
                    status="prazo_esgotado_antes_do_marco",
                    suspended_days=suspended_days,
                )
            )
            final_status = "prazo_esgotado_no_calculo"
            final_deadline = deadline
            break
        intervals.append(
            PrescriptionInterval(
                start_date=current_start,
                deadline=deadline,
                end_date=event.event_date,
                end_reason=event.event_type,
                status="interrompido_em_tempo",
                suspended_days=suspended_days,
            )
        )
        current_start = event.event_date
    else:
        deadline, suspended_days = _deadline_with_suspensions(
            current_start,
            applied_period,
            closed_suspensions,
            calculation.reference_date,
        )
        if calculation.reference_date > deadline:
            final_status = "prazo_esgotado_no_calculo"
        elif calculation.reference_date == deadline:
            final_status = "vence_na_data_referencia"
        intervals.append(
            PrescriptionInterval(
                start_date=current_start,
                deadline=deadline,
                end_date=calculation.reference_date,
                end_reason="data_referencia",
                status=final_status,
                suspended_days=suspended_days,
            )
        )
        final_deadline = deadline

    days_to_deadline = (
        (final_deadline - calculation.reference_date).days
        if final_deadline is not None
        else None
    )
    return OffensePrescriptionResult(
        offense_id=offense.offense_id,
        description=offense.description,
        article=offense.article,
        status=final_status,
        base_period_months=base_period,
        applied_period_months=applied_period,
        article_115_reduction_applied=bool(reduction_reasons),
        article_115_reasons=tuple(reduction_reasons),
        final_deadline=final_deadline,
        days_to_deadline=days_to_deadline,
        intervals=tuple(intervals),
        missing_fields=(),
        warnings=tuple(warnings),
    )


def _article_115_reduction(
    calculation: PrescriptionCalculationInput,
    offense: OffensePrescriptionInput,
) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    reasons: list[str] = []
    birth_date = calculation.defendant_birth_date
    if birth_date is None:
        missing.append("Data de nascimento do reu para avaliar o art. 115 do Codigo Penal.")
        return missing, reasons

    if _age_on_date(birth_date, offense.fact_date) < 21:
        reasons.append("reu_menor_de_21_na_data_do_fato")

    if calculation.sentence_status == "proferida":
        sentence_date = calculation.conviction_sentence_date
        if sentence_date is None:
            missing.append("Data da sentenca condenatoria informada como proferida.")
        elif _age_on_date(birth_date, sentence_date) > 70:
            reasons.append("reu_maior_de_70_na_data_da_sentenca")
    elif calculation.sentence_status == "desconhecida":
        if _age_on_date(birth_date, calculation.reference_date) > 70:
            missing.append(
                "Situacao e data da sentenca para avaliar se o reu tinha mais de 70 anos."
            )

    if reasons and offense.fact_date >= ARTICLE_115_EXCEPTION_EFFECTIVE_DATE:
        if offense.sexual_violence_against_woman is None:
            missing.append(
                "Confirmacao sobre violencia sexual contra mulher para aplicar a redacao "
                "vigente do art. 115 do Codigo Penal."
            )
        elif offense.sexual_violence_against_woman:
            reasons.clear()
    return missing, reasons


def _validate_calculation(calculation: PrescriptionCalculationInput) -> None:
    if not calculation.offenses:
        raise InvalidPrescriptionInput("Informe ao menos um delito.")
    if calculation.sentence_status not in {"nao_proferida", "proferida", "desconhecida"}:
        raise InvalidPrescriptionInput("Situacao da sentenca invalida.")
    if (
        calculation.sentence_status == "nao_proferida"
        and calculation.conviction_sentence_date is not None
    ):
        raise InvalidPrescriptionInput(
            "Nao informe data de sentenca quando a sentenca nao foi proferida."
        )
    if calculation.defendant_birth_date is not None:
        if calculation.defendant_birth_date > calculation.reference_date:
            raise InvalidPrescriptionInput("A data de nascimento nao pode estar no futuro.")
    sentence_date = calculation.conviction_sentence_date
    if calculation.sentence_status != "proferida" and sentence_date is not None:
        raise InvalidPrescriptionInput(
            "A data da sentenca exige situacao da sentenca igual a proferida."
        )
    if sentence_date is not None and sentence_date > calculation.reference_date:
        raise InvalidPrescriptionInput("A data da sentenca nao pode estar no futuro.")
    offense_ids = [offense.offense_id for offense in calculation.offenses]
    if len(offense_ids) != len(set(offense_ids)):
        raise InvalidPrescriptionInput("Os identificadores dos delitos devem ser unicos.")
    for offense in calculation.offenses:
        _validate_offense(calculation, offense)


def _validate_offense(
    calculation: PrescriptionCalculationInput,
    offense: OffensePrescriptionInput,
) -> None:
    prescription_period_months(offense.maximum_penalty_months)
    if offense.initial_term_type not in _INITIAL_TERM_TYPES:
        raise InvalidPrescriptionInput(
            f"Tipo de termo inicial nao suportado: {offense.initial_term_type}."
        )
    if offense.fact_date > calculation.reference_date:
        raise InvalidPrescriptionInput(
            f"A data do fato do delito {offense.offense_id} esta no futuro."
        )
    if offense.initial_term_date < offense.fact_date:
        raise InvalidPrescriptionInput(
            f"O termo inicial do delito {offense.offense_id} antecede a data do fato."
        )
    if offense.initial_term_date > calculation.reference_date:
        raise InvalidPrescriptionInput(
            f"O termo inicial do delito {offense.offense_id} esta no futuro."
        )
    if (
        calculation.conviction_sentence_date is not None
        and calculation.conviction_sentence_date < offense.initial_term_date
    ):
        raise InvalidPrescriptionInput(
            f"A sentenca antecede o termo inicial do delito {offense.offense_id}."
        )
    previous_event_date: date | None = None
    has_conviction_milestone = False
    for event in sorted(offense.interruptive_milestones, key=lambda item: item.event_date):
        if event.event_type not in _INTERRUPTIVE_EVENT_TYPES:
            raise InvalidPrescriptionInput(
                f"Marco interruptivo nao suportado: {event.event_type}."
            )
        if event.event_date < offense.initial_term_date:
            raise InvalidPrescriptionInput(
                f"Marco interruptivo anterior ao termo inicial no delito {offense.offense_id}."
            )
        if event.event_date > calculation.reference_date:
            raise InvalidPrescriptionInput(
                f"Marco interruptivo futuro no delito {offense.offense_id}."
            )
        if previous_event_date == event.event_date:
            raise InvalidPrescriptionInput(
                f"Ha marcos interruptivos na mesma data no delito {offense.offense_id}."
            )
        if event.event_type in {
            "sentenca_condenatoria_recorrivel",
            "acordao_condenatorio_recorrivel",
        }:
            has_conviction_milestone = True
        previous_event_date = event.event_date
    if has_conviction_milestone and calculation.sentence_status != "proferida":
        raise InvalidPrescriptionInput(
            "Marco condenatorio informado sem situacao da sentenca igual a proferida."
        )
    for period in offense.suspension_periods:
        if period.suspension_type not in _SUSPENSION_TYPES:
            raise InvalidPrescriptionInput(
                f"Tipo de suspensao nao suportado: {period.suspension_type}."
            )
        if period.start_date < offense.initial_term_date:
            raise InvalidPrescriptionInput(
                f"Suspensao anterior ao termo inicial no delito {offense.offense_id}."
            )
        if period.start_date > calculation.reference_date:
            raise InvalidPrescriptionInput(
                f"Suspensao futura no delito {offense.offense_id}."
            )
        if period.end_date is not None:
            if period.end_date <= period.start_date:
                raise InvalidPrescriptionInput(
                    f"Fim da suspensao deve ser posterior ao inicio no delito "
                    f"{offense.offense_id}."
                )
            if period.end_date > calculation.reference_date:
                raise InvalidPrescriptionInput(
                    f"Fim de suspensao futuro no delito {offense.offense_id}."
                )
            for event in offense.interruptive_milestones:
                if period.start_date <= event.event_date < period.end_date:
                    raise InvalidPrescriptionInput(
                        f"Marco interruptivo dentro de suspensao no delito "
                        f"{offense.offense_id}; revise as datas."
                    )


def _merged_suspensions(
    periods: tuple[SuspensionPeriod, ...],
) -> tuple[tuple[date, date], ...]:
    closed = sorted(
        (
            (item.start_date, item.end_date)
            for item in periods
            if item.end_date is not None
        ),
        key=lambda item: item[0],
    )
    merged: list[tuple[date, date]] = []
    for start, end_value in closed:
        end = end_value
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
            continue
        previous_start, previous_end = merged[-1]
        merged[-1] = (previous_start, max(previous_end, end))
    return tuple(merged)


def _deadline_with_suspensions(
    interval_start: date,
    period_months: int,
    suspensions: tuple[tuple[date, date], ...],
    interval_end: date,
) -> tuple[date, int]:
    deadline = _add_months(interval_start, period_months) - timedelta(days=1)
    suspended_days = 0
    for start, end in suspensions:
        if start >= interval_end:
            continue
        overlap_start = max(start, interval_start)
        if end <= overlap_start or overlap_start > deadline:
            continue
        duration = (end - overlap_start).days
        deadline += timedelta(days=duration)
        suspended_days += duration
    return deadline, suspended_days


def _add_months(value: date, months: int) -> date:
    absolute_month = value.year * 12 + (value.month - 1) + months
    year, month_index = divmod(absolute_month, 12)
    month = month_index + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _age_on_date(birth_date: date, reference_date: date) -> int:
    if birth_date > reference_date:
        raise InvalidPrescriptionInput("A data de nascimento e posterior ao marco avaliado.")
    birthday_passed = (reference_date.month, reference_date.day) >= (
        birth_date.month,
        birth_date.day,
    )
    return reference_date.year - birth_date.year - (0 if birthday_passed else 1)
