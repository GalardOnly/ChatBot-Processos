from __future__ import annotations

from dataclasses import dataclass

from preparador_audiencia.pdf_extraction import PageExtraction

DEFAULT_MAX_CHARS = 1800
DEFAULT_OVERLAP_CHARS = 180


@dataclass(frozen=True)
class TextChunk:
    page_number: int
    chunk_index: int
    text: str
    document_type: str | None = None


def chunk_extracted_pages(
    pages: list[PageExtraction],
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    for page in pages:
        text = page.full_text.strip()
        if not text:
            continue
        page_chunks = split_text(text, max_chars=max_chars, overlap_chars=overlap_chars)
        for chunk_index, chunk_text in enumerate(page_chunks):
            chunks.append(
                TextChunk(
                    page_number=page.page_number,
                    chunk_index=chunk_index,
                    text=chunk_text,
                    document_type=detect_document_type(chunk_text),
                )
            )
    return chunks


def split_text(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    if max_chars <= 0:
        raise ValueError("max_chars deve ser positivo")
    if overlap_chars < 0:
        raise ValueError("overlap_chars nao pode ser negativo")
    if overlap_chars >= max_chars:
        raise ValueError("overlap_chars deve ser menor que max_chars")

    normalized = text.strip()
    if len(normalized) <= max_chars:
        return [normalized]

    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + max_chars, len(normalized))
        chunks.append(normalized[start:end].strip())
        if end == len(normalized):
            break
        start = end - overlap_chars
    return chunks


def detect_document_type(text: str) -> str | None:
    lowered = text.lower()
    if "edital" in lowered:
        return "edital"
    if "decisao" in lowered or "decisão" in lowered:
        return "decisao"
    if "audiencia" in lowered or "audiência" in lowered:
        return "audiencia"
    if "sentenca" in lowered or "sentença" in lowered:
        return "sentenca"
    return None

