from dataclasses import replace

from preparador_audiencia.chunking import chunk_extracted_pages, detect_document_type, split_text
from preparador_audiencia.pdf_extraction import PageExtraction


def page(page_number: int, text: str) -> PageExtraction:
    return PageExtraction(
        page_number=page_number,
        char_count=len(text),
        word_count=len(text.split()),
        native_char_count=len(text),
        image_count=0,
        ocr_applied=False,
        ocr_char_count=0,
        extraction_method="native" if text else "empty",
        full_text=text,
        text_sample=text[:500],
        is_probably_empty=not text,
        quality_notes=["texto_nativo_extraido"] if text else ["sem_texto_nativo"],
    )


def test_split_text_uses_overlap() -> None:
    chunks = split_text("abcdefghij", max_chars=6, overlap_chars=2)

    assert chunks == ["abcdef", "efghij"]


def test_chunk_extracted_pages_preserves_page_and_chunk_index() -> None:
    chunks = chunk_extracted_pages(
        [page(3, "Audiencia " + "x" * 12)],
        max_chars=10,
        overlap_chars=2,
    )

    assert [(chunk.page_number, chunk.chunk_index) for chunk in chunks] == [(3, 0), (3, 1), (3, 2)]
    assert chunks[0].document_type == "audiencia"


def test_chunk_extracted_pages_skips_empty_pages() -> None:
    assert chunk_extracted_pages([page(1, "")]) == []


def test_chunk_extracted_pages_preserves_ocr_provenance() -> None:
    extracted_page = replace(
        page(4, "Depoimento da testemunha"),
        ocr_applied=True,
        ocr_engine="easyocr",
        ocr_engine_version="1.7.2",
        ocr_device="gpu",
        ocr_cache_hit=True,
        ocr_fallback_used=False,
    )

    chunk = chunk_extracted_pages([extracted_page])[0]

    assert chunk.ocr_engine == "easyocr"
    assert chunk.ocr_engine_version == "1.7.2"
    assert chunk.ocr_device == "gpu"
    assert chunk.ocr_cache_hit is True
    assert chunk.ocr_fallback_used is False


def test_detect_document_type_returns_none_when_unknown() -> None:
    assert detect_document_type("texto generico") is None
