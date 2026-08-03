from preparador_audiencia.ocr_benchmark_cli import (
    _easyocr_text_without_marginal_artifacts,
)


def test_easyocr_layout_filter_removes_vertical_margin_artifacts() -> None:
    results = [
        (
            [[100.0, 100.0], [500.0, 100.0], [500.0, 140.0], [100.0, 140.0]],
            "TERMO DE DEPOIMENTO EM AUTO DE PRISAO EM",
            0.95,
        ),
        (
            [[970.0, 90.0], [990.0, 90.0], [990.0, 300.0], [970.0, 300.0]],
            "1",
            0.20,
        ),
        (
            [[100.0, 150.0], [600.0, 150.0], [600.0, 190.0], [100.0, 190.0]],
            "FLAGRANTE QUE PRESTA A TESTEMUNHA",
            0.90,
        ),
    ]

    text = _easyocr_text_without_marginal_artifacts(results, image_width=1_000)

    assert text == (
        "TERMO DE DEPOIMENTO EM AUTO DE PRISAO EM\n"
        "FLAGRANTE QUE PRESTA A TESTEMUNHA"
    )
