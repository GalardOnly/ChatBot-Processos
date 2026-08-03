import json

import fitz

from preparador_audiencia.pdf_extraction import extract_pdf_report, normalize_text


class FakeOcrEngine:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    def extract_page_text(self, page: fitz.Page, zoom: float = 2.0) -> str:
        self.calls += 1
        return self.text


def create_pdf(path) -> None:
    document = fitz.open()

    page_1 = document.new_page()
    page_1.insert_text(
        (72, 72),
        "Processo 0001234-56.2026.8.14.0000\nAudiencia designada para 15/08/2026.",
    )

    document.new_page()

    page_3 = document.new_page()
    page_3.insert_text((72, 72), "OK")

    document.save(path)
    document.close()


def test_extract_pdf_report_preserves_page_numbers_and_quality_notes(tmp_path) -> None:
    pdf_path = tmp_path / "processo.pdf"
    create_pdf(pdf_path)

    report = extract_pdf_report(pdf_path)

    assert report.file_name == "processo.pdf"
    assert report.page_count == 3
    assert [page.page_number for page in report.pages] == [1, 2, 3]
    assert "Audiencia designada" in report.pages[0].text_sample
    assert report.pages[0].image_count == 0
    assert report.pages[1].is_probably_empty is True
    assert "sem_texto_nativo" in report.pages[1].quality_notes
    assert "baixo_texto_extraido" in report.pages[2].quality_notes


def test_extract_pdf_report_flags_image_page_with_sparse_text(tmp_path) -> None:
    pdf_path = tmp_path / "digitalizado.pdf"
    image_path = tmp_path / "scan.png"

    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 300, 120), 0)
    pixmap.save(image_path)

    document = fitz.open()
    page = document.new_page()
    page.insert_image(fitz.Rect(72, 120, 372, 240), filename=image_path)
    page.insert_text((72, 72), "Documento digitalizado juntado ao processo")
    document.save(pdf_path)
    document.close()

    report = extract_pdf_report(pdf_path, ocr_enabled=False)

    assert report.pages[0].image_count == 1
    assert report.pages[0].quality_notes == [
        "imagem_com_texto_curto",
        "provavel_necessidade_de_ocr",
    ]


def test_extract_pdf_report_applies_ocr_to_image_page_with_sparse_text(tmp_path) -> None:
    pdf_path = tmp_path / "digitalizado.pdf"
    image_path = tmp_path / "scan.png"
    fake_ocr = FakeOcrEngine("EDITAL DE CITACAO\nPrazo de 20 dias")

    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 300, 120), 0)
    pixmap.save(image_path)

    document = fitz.open()
    page = document.new_page()
    page.insert_image(fitz.Rect(72, 120, 372, 240), filename=image_path)
    page.insert_text((72, 72), "Documento digitalizado juntado ao processo")
    document.save(pdf_path)
    document.close()

    report = extract_pdf_report(pdf_path, ocr_engine=fake_ocr)

    assert fake_ocr.calls == 1
    assert report.pages[0].ocr_applied is True
    assert report.pages[0].ocr_char_count == len("EDITAL DE CITACAO\nPrazo de 20 dias")
    assert report.pages[0].extraction_method == "native_plus_ocr"
    assert "EDITAL DE CITACAO" in report.pages[0].text_sample
    assert "ocr_aplicado" in report.pages[0].quality_notes
    assert "ocr_com_texto" in report.pages[0].quality_notes
    assert report.pages[0].source_confidence == "baixa"
    assert "confianca_baixa" in report.pages[0].quality_notes


def test_extract_pdf_report_does_not_apply_ocr_to_text_page(tmp_path) -> None:
    pdf_path = tmp_path / "processo.pdf"
    fake_ocr = FakeOcrEngine("nao deveria chamar")
    create_pdf(pdf_path)

    report = extract_pdf_report(pdf_path, ocr_engine=fake_ocr)

    assert fake_ocr.calls == 0
    assert report.pages[0].ocr_applied is False
    assert report.pages[0].extraction_method == "native"


def test_extract_pdf_report_is_json_serializable(tmp_path) -> None:
    pdf_path = tmp_path / "processo.pdf"
    create_pdf(pdf_path)

    payload = extract_pdf_report(pdf_path).to_dict()

    encoded = json.dumps(payload, ensure_ascii=False)
    assert "processo.pdf" in encoded
    assert payload["empty_page_count"] == 1


def test_extract_pdf_report_reports_page_progress(tmp_path) -> None:
    pdf_path = tmp_path / "processo.pdf"
    create_pdf(pdf_path)
    progress = []

    report = extract_pdf_report(
        pdf_path,
        progress_callback=lambda current, total: progress.append((current, total)),
    )

    assert report.page_count == 3
    assert progress == [(1, 3), (2, 3), (3, 3)]


def test_normalize_text_removes_excess_blank_lines_and_spaces() -> None:
    assert normalize_text(" A   B \n\n C\r\n") == "A B\nC"


def test_ocr_with_substantial_text_is_marked_for_review(tmp_path) -> None:
    pdf_path = tmp_path / "digitalizado-longo.pdf"
    image_path = tmp_path / "scan.png"
    ocr_text = " ".join(
        ["A decisao registra fatos, datas e fundamentos que devem ser conferidos."]
        * 6
    )
    fake_ocr = FakeOcrEngine(ocr_text)

    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 300, 120), 0)
    pixmap.save(image_path)
    document = fitz.open()
    page = document.new_page()
    page.insert_image(fitz.Rect(72, 120, 372, 240), filename=image_path)
    document.save(pdf_path)
    document.close()

    report = extract_pdf_report(pdf_path, ocr_engine=fake_ocr)

    assert report.pages[0].source_confidence == "media"
    assert "confianca_media" in report.pages[0].quality_notes


def test_ocr_replaces_long_native_text_with_glued_words(tmp_path) -> None:
    pdf_path = tmp_path / "texto-colado.pdf"
    glued_lines = "\n".join(["palavracolada" * 10] * 12)
    ocr_text = " ".join(
        ["A vitima declarou os fatos de forma legivel e completa para conferencia."]
        * 5
    )
    fake_ocr = FakeOcrEngine(ocr_text)
    document = fitz.open()
    page = document.new_page()
    page.insert_text((20, 20), glued_lines, fontsize=5)
    document.save(pdf_path)
    document.close()

    report = extract_pdf_report(pdf_path, ocr_engine=fake_ocr)
    extracted = report.pages[0]

    assert fake_ocr.calls == 1
    assert extracted.full_text == ocr_text
    assert extracted.extraction_method == "ocr_recovery"
    assert extracted.source_confidence == "media"
    assert "texto_nativo_com_palavras_coladas" in extracted.quality_notes
    assert "ocr_substituiu_texto_nativo_inadequado" in extracted.quality_notes


def test_substantial_ocr_replaces_sparse_native_image_layer(tmp_path) -> None:
    pdf_path = tmp_path / "pagina-digitalizada.pdf"
    image_path = tmp_path / "scan.png"
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 300, 120), 0)
    pixmap.save(image_path)
    ocr_text = " ".join(
        ["A testemunha prestou declaracao completa durante o inquerito policial."]
        * 5
    )
    fake_ocr = FakeOcrEngine(ocr_text)
    document = fitz.open()
    page = document.new_page()
    page.insert_image(fitz.Rect(72, 120, 372, 240), filename=image_path)
    page.insert_text((72, 72), "Camada nativa incompleta")
    document.save(pdf_path)
    document.close()

    extracted = extract_pdf_report(pdf_path, ocr_engine=fake_ocr).pages[0]

    assert extracted.full_text == ocr_text
    assert extracted.extraction_method == "ocr_recovery"
    assert extracted.source_confidence == "media"


def test_ocr_with_many_glued_words_has_low_confidence(tmp_path) -> None:
    pdf_path = tmp_path / "ocr-ainda-ilegivel.pdf"
    image_path = tmp_path / "scan.png"
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 300, 120), 0)
    pixmap.save(image_path)
    glued_ocr = "\n".join(["depoimentosemespacos" * 4] * 25)
    fake_ocr = FakeOcrEngine(glued_ocr)
    document = fitz.open()
    page = document.new_page()
    page.insert_image(fitz.Rect(72, 120, 372, 240), filename=image_path)
    page.insert_text((72, 72), "Camada nativa incompleta")
    document.save(pdf_path)
    document.close()

    extracted = extract_pdf_report(pdf_path, ocr_engine=fake_ocr).pages[0]

    assert extracted.full_text == glued_ocr
    assert extracted.source_confidence == "baixa"
    assert "ocr_com_palavras_coladas" in extracted.quality_notes
