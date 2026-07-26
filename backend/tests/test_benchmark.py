import json

import fitz

from preparador_audiencia.benchmark import (
    BenchmarkSource,
    download_pdf_source,
    load_benchmark_sources,
    render_sources_table,
    run_juristcu_benchmark,
    run_pdf_benchmark,
    sources_by_kind,
)


def test_load_benchmark_sources_reads_manifest(tmp_path) -> None:
    manifest = tmp_path / "sources.json"
    manifest.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "id": "juristcu",
                        "title": "JurisTCU",
                        "kind": "dataset",
                        "origin": "nao oficial",
                        "url": "https://example.com/dataset",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    sources = load_benchmark_sources(manifest)

    assert sources[0].id == "juristcu"
    assert sources[0].kind == "dataset"


def test_sources_by_kind_filters_manifest_entries() -> None:
    sources = [
        BenchmarkSource(
            id="dataset",
            title="Dataset",
            kind="dataset",
            origin="nao oficial",
            url="https://example.com/dataset",
        ),
        BenchmarkSource(
            id="pdf",
            title="PDF",
            kind="pdf",
            origin="oficial",
            url="https://example.com/documento.pdf",
        ),
    ]

    assert [source.id for source in sources_by_kind(sources, "pdf")] == ["pdf"]
    assert sources_by_kind(sources, None) == sources


def test_download_pdf_source_writes_pdf_with_injected_fetcher(tmp_path) -> None:
    source = BenchmarkSource(
        id="amostra",
        title="Amostra",
        kind="pdf",
        origin="nao oficial",
        url="https://example.com/amostra.pdf",
    )

    result = download_pdf_source(source, tmp_path, fetcher=lambda _: b"%PDF-1.7\nconteudo")

    assert result.skipped is False
    assert result.bytes_written == 17
    assert (tmp_path / "amostra.pdf").exists()


def test_download_pdf_source_rejects_non_pdf_content(tmp_path) -> None:
    source = BenchmarkSource(
        id="html",
        title="HTML",
        kind="pdf",
        origin="nao oficial",
        url="https://example.com/amostra.pdf",
    )

    result = download_pdf_source(source, tmp_path, fetcher=lambda _: b"<html></html>")

    assert result.skipped is True
    assert result.path is None


def test_render_sources_table_shows_key_fields() -> None:
    table = render_sources_table(
        [
            BenchmarkSource(
                id="juristcu",
                title="JurisTCU",
                kind="dataset",
                origin="nao oficial",
                url="https://example.com",
            )
        ]
    )

    assert "juristcu" in table
    assert "nao oficial" in table


def test_run_juristcu_benchmark_with_local_fixture(tmp_path, monkeypatch) -> None:
    cache = tmp_path / "juristcu"
    cache.mkdir()
    (cache / "query.csv").write_text(
        "ID,TEXT,SOURCE\n1,regularidade fiscal,fixture\n",
        encoding="utf-8",
    )
    (cache / "qrel.csv").write_text(
        "QUERY_ID,DOC_ID,SCORE,ENGINE,RANK\n1,doc-relevante,3,fixture,1\n",
        encoding="utf-8",
    )
    (cache / "doc.csv").write_text(
        "\n".join(
            [
                "KEY,AREA,TEMA,SUBTEMA,ENUNCIADO,EXCERTO,INDEXADORESCONSOLIDADOS,REFERENCIALEGAL",
                "doc-relevante,Licitacao,Habilitacao,Documentacao,regularidade fiscal,"
                "certidao de regularidade fiscal,regularidade fiscal,Lei 8666",
                "doc-ruido,Pessoal,Aposentadoria,Tempo,aposentadoria especial,"
                "tempo de servico,aposentadoria,Lei 8112",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "preparador_audiencia.benchmark.ensure_juristcu_files",
        lambda cache_dir: {
            "doc.csv": cache / "doc.csv",
            "query.csv": cache / "query.csv",
            "qrel.csv": cache / "qrel.csv",
        },
    )
    monkeypatch.setenv("PREPARADOR_CHROMA_DIR", str(tmp_path / "chroma"))

    report = run_juristcu_benchmark(
        cache_dir=cache,
        query_limit=1,
        distractor_limit=1,
        embedding_model="hash",
        top_k=1,
    )

    assert report.dataset == "LeandroRibeiro/JurisTCU"
    assert report.hit_rate == 1.0
    assert report.cases[0].top_doc_ids == ["doc-relevante"]
    assert report.rebuilt_indexes == ["hash"]


def test_run_juristcu_benchmark_reuses_existing_index(tmp_path, monkeypatch) -> None:
    cache = tmp_path / "juristcu"
    cache.mkdir()
    (cache / "query.csv").write_text(
        "ID,TEXT,SOURCE\n1,regularidade fiscal,fixture\n",
        encoding="utf-8",
    )
    (cache / "qrel.csv").write_text(
        "QUERY_ID,DOC_ID,SCORE,ENGINE,RANK\n1,doc-relevante,3,fixture,1\n",
        encoding="utf-8",
    )
    (cache / "doc.csv").write_text(
        "\n".join(
            [
                "KEY,AREA,TEMA,SUBTEMA,ENUNCIADO,EXCERTO,INDEXADORESCONSOLIDADOS,REFERENCIALEGAL",
                "doc-relevante,Licitacao,Habilitacao,Documentacao,regularidade fiscal,"
                "certidao de regularidade fiscal,regularidade fiscal,Lei 8666",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "preparador_audiencia.benchmark.ensure_juristcu_files",
        lambda cache_dir: {
            "doc.csv": cache / "doc.csv",
            "query.csv": cache / "query.csv",
            "qrel.csv": cache / "qrel.csv",
        },
    )
    monkeypatch.setenv("PREPARADOR_CHROMA_DIR", str(tmp_path / "chroma"))
    run_juristcu_benchmark(
        cache_dir=cache,
        query_limit=1,
        distractor_limit=0,
        embedding_model="hash",
        top_k=1,
    )

    report = run_juristcu_benchmark(
        cache_dir=cache,
        query_limit=1,
        distractor_limit=0,
        embedding_model="hash",
        top_k=1,
    )

    assert report.reused_indexes == ["hash"]
    assert report.rebuilt_indexes == []


def test_run_pdf_benchmark_extracts_local_pdf(tmp_path) -> None:
    pdf_path = tmp_path / "processo.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Processo de teste para benchmark.")
    pdf_path.write_bytes(document.tobytes())
    document.close()

    report = run_pdf_benchmark(
        [pdf_path],
        family="fixture",
        ocr_enabled=False,
        max_pages=1,
    )

    assert report.family == "fixture"
    assert report.files[0].file_name == "processo.pdf"
    assert report.files[0].processed_pages == 1
    assert report.files[0].total_char_count > 0
