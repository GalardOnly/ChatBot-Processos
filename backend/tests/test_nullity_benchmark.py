from preparador_audiencia.legal_catalog import load_legal_topic
from preparador_audiencia.nullity_analysis import (
    CONCLUSION_LABELS,
    NullityAnalysisResult,
    RequirementAssessment,
)
from preparador_audiencia.nullity_benchmark import (
    NullityBenchmarkSuite,
    estimate_nullity_llm_calls,
    load_nullity_benchmark_suite,
    run_nullity_benchmark,
)


def test_loads_controlled_recognition_suite() -> None:
    suite = load_nullity_benchmark_suite()

    assert suite.id == "reconhecimento-pessoas-controlado-v1"
    assert suite.legal_review_status == "pending"
    assert len(suite.cases) == 6
    assert len({case.id for case in suite.cases}) == 6
    assert estimate_nullity_llm_calls(len(suite.cases), 2) == 12


def test_benchmark_scores_expected_conclusion_requirements_and_pages() -> None:
    suite = load_nullity_benchmark_suite()
    case = suite.cases[0]

    def analyzer(sources, **kwargs) -> NullityAnalysisResult:
        assessments = tuple(
            RequirementAssessment(
                id=requirement_id,
                category=(
                    "aplicabilidade"
                    if requirement_id == "pessoa_desconhecida"
                    else "validade"
                ),
                label=requirement_id,
                condition="Aplicavel.",
                result=result,
                justification="Resultado controlado.",
                pages=case.expected.requirement_pages.get(requirement_id, ()),
                legal_source_ids=("stj_tema_1258",),
            )
            for requirement_id, result in case.expected.requirement_results.items()
        )
        return _analysis_result(
            conclusion=case.expected.conclusion,
            impact=case.expected.procedural_impact,
            impact_pages=case.expected.impact_pages,
            requirements=assessments,
        )

    report = run_nullity_benchmark(
        _single_case_suite(suite, 0),
        ["gemini:test"],
        analyzer=analyzer,
    )

    result = report.models[0]
    assert result.conclusion_accuracy == 1.0
    assert result.impact_accuracy == 1.0
    assert result.requirement_accuracy == 1.0
    assert result.page_reference_accuracy == 1.0
    assert result.average_weighted_score == 100.0
    assert result.gate_passed is True


def test_benchmark_blocks_gate_on_false_positive_invalidity() -> None:
    suite = load_nullity_benchmark_suite()
    case = suite.cases[2]

    def analyzer(sources, **kwargs) -> NullityAnalysisResult:
        return _analysis_result(
            conclusion="forte_fundamento_para_alegar_invalidade",
            impact=case.expected.procedural_impact,
            impact_pages=(),
            requirements=(
                RequirementAssessment(
                    id="pessoa_desconhecida",
                    category="aplicabilidade",
                    label="Pessoa desconhecida",
                    condition="Aplicavel.",
                    result="nao_observado",
                    justification="A pessoa era conhecida.",
                    pages=(6,),
                    legal_source_ids=("stj_tema_1258",),
                ),
            ),
        )

    report = run_nullity_benchmark(
        _single_case_suite(suite, 2),
        ["groq:test"],
        analyzer=analyzer,
    )

    result = report.models[0]
    assert result.false_positive_invalidity_count == 1
    assert result.gate_passed is False


def _single_case_suite(
    suite: NullityBenchmarkSuite,
    index: int,
) -> NullityBenchmarkSuite:
    return NullityBenchmarkSuite(
        id=suite.id,
        description=suite.description,
        legal_review_status=suite.legal_review_status,
        cases=(suite.cases[index],),
    )


def _analysis_result(
    *,
    conclusion,
    impact: str,
    impact_pages: tuple[int, ...],
    requirements: tuple[RequirementAssessment, ...],
) -> NullityAnalysisResult:
    topic = load_legal_topic("reconhecimento_pessoas")
    return NullityAnalysisResult(
        topic=topic.id,
        title=topic.title,
        conclusion=conclusion,
        conclusion_label=CONCLUSION_LABELS[conclusion],
        confidence="alta",
        summary="Analise controlada.",
        applicability="sim",
        applicability_summary="Aplicavel.",
        procedural_impact=impact,
        impact_summary="Impacto controlado.",
        impact_pages=impact_pages,
        requirements=requirements,
        next_steps=(),
        gaps=(),
        model="modelo:test",
        fallback_used=False,
        process_sources=(),
        legal_sources=topic.sources,
        legal_catalog_version=topic.version,
        legal_catalog_verified_at=topic.verified_at,
        warnings=(),
    )
