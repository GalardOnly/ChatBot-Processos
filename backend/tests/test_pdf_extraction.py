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
