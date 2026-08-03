from pathlib import Path

from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.dossier_validation import (
    render_dossier_validation_markdown,
    validate_hearing_dossier,
    write_dossier_validation_report,
)
from preparador_audiencia.hearing_dossier_repository import HearingDossierRepository
from preparador_audiencia.repositories import ProcessoRepository, utc_now_text


def _prepared_dossier(tmp_path):
    connection = connect_database(tmp_path / "test.sqlite3")
    initialize_database(connection)
    ProcessoRepository(connection).create_pending(
        "proc_1",
        "processo.pdf",
        "storage/processo.pdf",
        "abc",
    )
    now = utc_now_text()
    connection.executemany(
        """
        INSERT INTO chunks (
            processo_id, page_number, chunk_index, text, document_type,
            source_confidence, vector_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?)
        """,
        [
            (
                "proc_1",
                14,
                0,
                "O fato ocorreu em 12/03/2018.",
                "denuncia",
                "alta",
                now,
            ),
            (
                "proc_1",
                21,
                0,
                "A vitima declarou que viu o autor.",
                "depoimento",
                "alta",
                now,
            ),
            (
                "proc_1",
                32,
                0,
                "Em juizo declarou que nao viu o rosto.",
                "depoimento",
                "alta",
                now,
            ),
        ],
    )
    connection.commit()
    repository = HearingDossierRepository(connection)
    repository.prepare("proc_1")
    repository.save_section(
        "proc_1",
        "marcos_essenciais",
        {
            "itens": [
                {
                    "tipo": "data_fato",
                    "valor": "12/03/2018",
                    "fontes": [_reference(14, 0, "O fato ocorreu em 12/03/2018.")],
                }
            ],
            "campos_para_confirmar": [],
            "avisos": [],
        },
        model="gemini:test",
        fallback_used=False,
    )
    repository.save_section(
        "proc_1",
        "depoimentos",
        {
            "itens": [
                {
                    "pessoa": "Vitima",
                    "trechos": [
                        {
                            "texto": "declarou que viu o autor",
                            "fonte": _reference(
                                21,
                                0,
                                "A vitima declarou que viu o autor.",
                            ),
                        }
                    ],
                }
            ],
            "lacunas": [],
            "avisos": [],
        },
        model="gemini:test",
        fallback_used=False,
    )
    repository.save_section(
        "proc_1",
        "contradicoes",
        {
            "itens": [
                {
                    "afirmacao_a": {
                        "texto": "viu o autor",
                        "fonte": _reference(
                            21,
                            0,
                            "A vitima declarou que viu o autor.",
                        ),
                    },
                    "afirmacao_b": {
                        "texto": "nao viu o rosto",
                        "fonte": _reference(
                            32,
                            0,
                            "Em juizo declarou que nao viu o rosto.",
                        ),
                    },
                }
            ],
            "lacunas": [],
            "avisos": [],
        },
        model="gemini:test",
        fallback_used=False,
    )
    return connection, repository.finish("proc_1")


def _reference(page: int, chunk: int, text: str) -> dict[str, object]:
    return {
        "pagina": page,
        "chunk_index": chunk,
        "tipo_documento": "depoimento",
        "confianca_fonte": "alta",
        "trecho": text,
    }


def test_validation_confirms_persisted_sources_and_literal_excerpts(tmp_path) -> None:
    connection, dossier = _prepared_dossier(tmp_path)

    report = validate_hearing_dossier(dossier, connection)

    assert report.passed is True
    assert report.verdict == "aprovado_estruturalmente"
    assert report.reference_checks == 4
    assert report.valid_references == 4
    assert report.literal_checks == 4
    assert report.valid_literals == 4
    assert report.findings == ()


def test_validation_detects_tampered_page_and_quote(tmp_path) -> None:
    connection, dossier = _prepared_dossier(tmp_path)
    connection.execute(
        "UPDATE hearing_dossier_sections SET payload_json = REPLACE(payload_json, ?, ?) "
        "WHERE processo_id = ? AND section_key = ?",
        ("12/03/2018", "31/12/2099", "proc_1", "marcos_essenciais"),
    )
    connection.commit()
    tampered = HearingDossierRepository(connection).get("proc_1")

    report = validate_hearing_dossier(tampered, connection)

    assert report.passed is False
    assert report.verdict == "falha_estrutural"
    assert {finding.code for finding in report.findings} >= {
        "source_excerpt_not_literal",
        "event_value_not_literal",
    }


def test_validation_report_writes_json_and_readable_markdown(tmp_path) -> None:
    connection, dossier = _prepared_dossier(tmp_path)
    report = validate_hearing_dossier(dossier, connection)
    output = tmp_path / "report.json"

    json_path, markdown_path = write_dossier_validation_report(report, output)

    assert json_path == output
    assert json_path.is_file()
    assert markdown_path.is_file()
    markdown = render_dossier_validation_markdown(report)
    assert "Referencias validas: 4/4" in markdown
    assert "Limite da validacao" in markdown
    assert Path(markdown_path).read_text(encoding="utf-8") == markdown


def test_validation_requests_review_when_useful_content_is_missing(tmp_path) -> None:
    connection, dossier = _prepared_dossier(tmp_path)
    repository = HearingDossierRepository(connection)
    repository.save_section(
        "proc_1",
        "marcos_essenciais",
        {
            "itens": dossier.sections[0].payload["itens"],
            "campos_para_confirmar": [
                {
                    "campo": "recebimento_denuncia",
                    "rotulo": "Data do recebimento da denuncia",
                    "motivo": "Nao localizada.",
                }
            ],
            "avisos": [],
        },
        model="gemini:test",
        fallback_used=False,
    )
    repository.save_section(
        "proc_1",
        "contradicoes",
        {"itens": [], "lacunas": [], "avisos": []},
        model="gemini:test",
        fallback_used=False,
    )
    dossier = repository.finish("proc_1")

    report = validate_hearing_dossier(dossier, connection)

    assert report.passed is True
    assert report.verdict == "aprovado_com_revisao"
    assert {finding.code for finding in report.findings} == {
        "essential_fields_missing",
        "no_supported_contradiction",
    }
