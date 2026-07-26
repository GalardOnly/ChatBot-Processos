from preparador_audiencia.quality_signals import inspect_response_grounding
from preparador_audiencia.search import SearchResult


def test_inspect_response_grounding_detects_supported_citations() -> None:
    signals = inspect_response_grounding(
        "A audiencia foi designada e precisa ser confirmada [p. 2].",
        [
            SearchResult(
                text="Audiencia designada.",
                page_number=2,
                chunk_index=0,
                document_type=None,
                score=0.9,
            )
        ],
    )

    assert signals.cited_pages == [2]
    assert signals.unsupported_cited_pages == []
    assert signals.rule_risk == "baixo"
    assert signals.uncertainty_markers == 1


def test_inspect_response_grounding_flags_unsupported_page() -> None:
    signals = inspect_response_grounding(
        "A decisao consta na pagina citada [p. 9].",
        [
            SearchResult(
                text="Decisao em outra pagina.",
                page_number=1,
                chunk_index=0,
                document_type=None,
                score=0.9,
            )
        ],
    )

    assert signals.unsupported_cited_pages == [9]
    assert signals.rule_risk == "alto"


def test_inspect_response_grounding_reads_grouped_page_citations() -> None:
    signals = inspect_response_grounding(
        "A decisao aparece nas fontes consultadas [p. 1, 7 e 9].",
        [
            SearchResult("Fonte 1.", 1, 0, None, 0.9),
            SearchResult("Fonte 7.", 7, 0, None, 0.9),
            SearchResult("Fonte 9.", 9, 0, None, 0.9),
        ],
    )

    assert signals.cited_pages == [1, 7, 9]
    assert signals.unsupported_cited_pages == []


def test_inspect_response_grounding_flags_many_uncited_claims() -> None:
    resposta = "\n".join(
        [
            "A primeira afirmacao longa aparece sem citacao de pagina suficiente.",
            "A segunda afirmacao longa tambem aparece sem fonte explicita.",
            "A terceira afirmacao longa continua sem referencia ao processo.",
        ]
    )

    signals = inspect_response_grounding(
        resposta,
        [
            SearchResult(
                text="Fonte recuperada.",
                page_number=1,
                chunk_index=0,
                document_type=None,
                score=0.9,
            )
        ],
    )

    assert signals.claim_lines == 3
    assert signals.citation_coverage == 0
    assert signals.rule_risk == "alto"
