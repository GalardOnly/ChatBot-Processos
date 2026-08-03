from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

from preparador_audiencia.hearing_dossier_repository import HearingDossierRecord


@dataclass(frozen=True)
class ValidationFinding:
    severity: str
    section: str
    code: str
    message: str
    page: int | None = None
    chunk_index: int | None = None


@dataclass(frozen=True)
class SectionValidation:
    key: str
    status: str
    item_count: int
    warning_count: int
    retrieval_ms: int | None
    generation_ms: int | None


@dataclass(frozen=True)
class DossierValidationReport:
    processo_id: str
    dossier_status: str
    verdict: str
    passed: bool
    reference_checks: int
    valid_references: int
    literal_checks: int
    valid_literals: int
    sections: tuple[SectionValidation, ...]
    findings: tuple[ValidationFinding, ...]

    @property
    def reference_accuracy(self) -> float:
        if not self.reference_checks:
            return 1.0
        return self.valid_references / self.reference_checks

    @property
    def literal_accuracy(self) -> float:
        if not self.literal_checks:
            return 1.0
        return self.valid_literals / self.literal_checks


@dataclass
class _Counters:
    reference_checks: int = 0
    valid_references: int = 0
    literal_checks: int = 0
    valid_literals: int = 0


def validate_hearing_dossier(
    dossier: HearingDossierRecord,
    connection: sqlite3.Connection,
) -> DossierValidationReport:
    chunks = _load_chunks(connection, dossier.processo_id)
    counters = _Counters()
    findings: list[ValidationFinding] = []
    section_reports: list[SectionValidation] = []
    section_payloads: dict[str, dict[str, object]] = {}

    for section in dossier.sections:
        section_payloads[section.key] = section.payload
        items = _list_value(section.payload, "itens")
        warnings = _list_value(section.payload, "avisos")
        section_reports.append(
            SectionValidation(
                key=section.key,
                status=section.status,
                item_count=len(items),
                warning_count=len(warnings),
                retrieval_ms=section.retrieval_ms,
                generation_ms=section.generation_ms,
            )
        )
        if section.status != "concluido":
            findings.append(
                ValidationFinding(
                    severity="erro",
                    section=section.key,
                    code="section_not_completed",
                    message=section.error_message or "A secao nao foi concluida.",
                )
            )
            continue
        if section.key == "marcos_essenciais":
            _validate_key_events(items, chunks, counters, findings)
        elif section.key == "depoimentos":
            _validate_testimonies(items, chunks, counters, findings)
        elif section.key == "contradicoes":
            _validate_contradictions(items, chunks, counters, findings)

    _add_utility_findings(section_reports, section_payloads, findings)
    error_count = sum(finding.severity == "erro" for finding in findings)
    warning_count = sum(finding.severity == "aviso" for finding in findings)
    passed = dossier.status == "concluido" and error_count == 0
    if not passed:
        verdict = "falha_estrutural"
    elif warning_count:
        verdict = "aprovado_com_revisao"
    else:
        verdict = "aprovado_estruturalmente"
    return DossierValidationReport(
        processo_id=dossier.processo_id,
        dossier_status=dossier.status,
        verdict=verdict,
        passed=passed,
        reference_checks=counters.reference_checks,
        valid_references=counters.valid_references,
        literal_checks=counters.literal_checks,
        valid_literals=counters.valid_literals,
        sections=tuple(section_reports),
        findings=tuple(findings),
    )


def write_dossier_validation_report(
    report: DossierValidationReport,
    output_path: Path,
) -> tuple[Path, Path]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(report)
    payload["reference_accuracy"] = report.reference_accuracy
    payload["literal_accuracy"] = report.literal_accuracy
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path = output_path.with_suffix(".md")
    markdown_path.write_text(render_dossier_validation_markdown(report), encoding="utf-8")
    return output_path, markdown_path


def render_dossier_validation_markdown(report: DossierValidationReport) -> str:
    lines = [
        "# Validacao do dossie de audiencia",
        "",
        f"Processo: `{report.processo_id}`",
        f"Status do dossie: `{report.dossier_status}`",
        f"Veredito tecnico: `{report.verdict}`",
        "",
        "## Metricas deterministicas",
        "",
        f"Referencias validas: {report.valid_references}/{report.reference_checks} "
        f"({report.reference_accuracy:.1%})",
        f"Trechos literais validos: {report.valid_literals}/{report.literal_checks} "
        f"({report.literal_accuracy:.1%})",
        "",
        "## Secoes",
        "",
        "| Secao | Status | Itens | Avisos | Recuperacao | Geracao |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    lines.extend(
        f"| {section.key} | {section.status} | {section.item_count} | "
        f"{section.warning_count} | {_format_ms(section.retrieval_ms)} | "
        f"{_format_ms(section.generation_ms)} |"
        for section in report.sections
    )
    lines.extend(["", "## Achados", ""])
    if not report.findings:
        lines.append("Nenhuma inconsistencia estrutural foi encontrada.")
    else:
        for finding in report.findings:
            location = ""
            if finding.page is not None:
                location = f" [p. {finding.page}, chunk {finding.chunk_index}]"
            lines.append(
                f"- **{finding.severity.upper()} | {finding.section} | "
                f"{finding.code}:** {finding.message}{location}"
            )
    lines.extend(
        [
            "",
            "## Limite da validacao",
            "",
            "Este relatorio confirma referencias, paginas e literalidade contra os chunks "
            "persistidos. Ele nao confirma se a selecao foi completa nem se a interpretacao "
            "juridica esta correta. Datas, autoria das falas e relevancia das contradicoes "
            "ainda precisam ser conferidas no PDF por um profissional.",
            "",
        ]
    )
    return "\n".join(lines)


def _validate_key_events(
    items: list[object],
    chunks: dict[tuple[int, int], sqlite3.Row],
    counters: _Counters,
    findings: list[ValidationFinding],
) -> None:
    for item in items:
        if not isinstance(item, dict):
            findings.append(_invalid_item("marcos_essenciais"))
            continue
        value = str(item.get("valor") or "").strip()
        references = _list_value(item, "fontes")
        valid_chunks = _validate_references(
            "marcos_essenciais",
            references,
            chunks,
            counters,
            findings,
        )
        counters.literal_checks += 1
        if value and any(_contains_excerpt(str(row["text"]), value) for row in valid_chunks):
            counters.valid_literals += 1
        else:
            findings.append(
                ValidationFinding(
                    severity="erro",
                    section="marcos_essenciais",
                    code="event_value_not_literal",
                    message=f"O valor do marco nao foi localizado nas fontes: {value!r}.",
                )
            )


def _validate_testimonies(
    items: list[object],
    chunks: dict[tuple[int, int], sqlite3.Row],
    counters: _Counters,
    findings: list[ValidationFinding],
) -> None:
    for item in items:
        if not isinstance(item, dict):
            findings.append(_invalid_item("depoimentos"))
            continue
        for excerpt in _list_value(item, "trechos"):
            if not isinstance(excerpt, dict):
                findings.append(_invalid_item("depoimentos"))
                continue
            text = str(excerpt.get("texto") or "").strip()
            reference = excerpt.get("fonte")
            valid_chunks = _validate_references(
                "depoimentos",
                [reference] if isinstance(reference, dict) else [],
                chunks,
                counters,
                findings,
            )
            _validate_literal(
                "depoimentos",
                "testimony_not_literal",
                text,
                valid_chunks,
                counters,
                findings,
            )


def _validate_contradictions(
    items: list[object],
    chunks: dict[tuple[int, int], sqlite3.Row],
    counters: _Counters,
    findings: list[ValidationFinding],
) -> None:
    for item in items:
        if not isinstance(item, dict):
            findings.append(_invalid_item("contradicoes"))
            continue
        for claim_key in ("afirmacao_a", "afirmacao_b"):
            claim = item.get(claim_key)
            if not isinstance(claim, dict):
                findings.append(_invalid_item("contradicoes"))
                continue
            text = str(claim.get("texto") or "").strip()
            reference = claim.get("fonte")
            valid_chunks = _validate_references(
                "contradicoes",
                [reference] if isinstance(reference, dict) else [],
                chunks,
                counters,
                findings,
            )
            _validate_literal(
                "contradicoes",
                "contradiction_claim_not_literal",
                text,
                valid_chunks,
                counters,
                findings,
            )


def _validate_references(
    section: str,
    references: list[object],
    chunks: dict[tuple[int, int], sqlite3.Row],
    counters: _Counters,
    findings: list[ValidationFinding],
) -> list[sqlite3.Row]:
    valid_chunks: list[sqlite3.Row] = []
    if not references:
        findings.append(
            ValidationFinding(
                severity="erro",
                section=section,
                code="source_missing",
                message="O item nao possui fonte processual.",
            )
        )
        return valid_chunks
    for reference in references:
        counters.reference_checks += 1
        if not isinstance(reference, dict):
            findings.append(_invalid_reference(section))
            continue
        page = _int_value(reference.get("pagina"))
        chunk_index = _int_value(reference.get("chunk_index"))
        row = (
            chunks.get((page, chunk_index))
            if page is not None and chunk_index is not None
            else None
        )
        if row is None:
            findings.append(
                ValidationFinding(
                    severity="erro",
                    section=section,
                    code="source_not_found",
                    message="A pagina e o chunk indicados nao existem para o processo.",
                    page=page,
                    chunk_index=chunk_index,
                )
            )
            continue
        excerpt = str(reference.get("trecho") or "").strip()
        if not excerpt or not _contains_excerpt(str(row["text"]), excerpt):
            findings.append(
                ValidationFinding(
                    severity="erro",
                    section=section,
                    code="source_excerpt_not_literal",
                    message="O trecho da referencia nao coincide com o chunk persistido.",
                    page=page,
                    chunk_index=chunk_index,
                )
            )
            continue
        if str(reference.get("confianca_fonte")) != str(row["source_confidence"]):
            findings.append(
                ValidationFinding(
                    severity="erro",
                    section=section,
                    code="source_confidence_mismatch",
                    message="A confianca informada difere da confianca persistida.",
                    page=page,
                    chunk_index=chunk_index,
                )
            )
            continue
        counters.valid_references += 1
        valid_chunks.append(row)
    return valid_chunks


def _validate_literal(
    section: str,
    code: str,
    text: str,
    valid_chunks: list[sqlite3.Row],
    counters: _Counters,
    findings: list[ValidationFinding],
) -> None:
    counters.literal_checks += 1
    if text and any(_contains_excerpt(str(row["text"]), text) for row in valid_chunks):
        counters.valid_literals += 1
        return
    findings.append(
        ValidationFinding(
            severity="erro",
            section=section,
            code=code,
            message="O trecho declarado como literal nao foi confirmado na fonte.",
        )
    )


def _add_utility_findings(
    sections: list[SectionValidation],
    payloads: dict[str, dict[str, object]],
    findings: list[ValidationFinding],
) -> None:
    by_key = {section.key: section for section in sections}
    for key, message in (
        ("marcos_essenciais", "Nenhum marco essencial foi extraido."),
        ("depoimentos", "Nenhum depoimento foi extraido."),
    ):
        section = by_key.get(key)
        if section is not None and section.status == "concluido" and not section.item_count:
            findings.append(
                ValidationFinding(
                    severity="aviso",
                    section=key,
                    code="empty_section",
                    message=message,
                )
            )
    key_event_gaps = _list_value(payloads.get("marcos_essenciais", {}), "campos_para_confirmar")
    if key_event_gaps:
        labels = [
            str(item.get("rotulo"))
            for item in key_event_gaps
            if isinstance(item, dict) and item.get("rotulo")
        ]
        findings.append(
            ValidationFinding(
                severity="aviso",
                section="marcos_essenciais",
                code="essential_fields_missing",
                message=(
                    "Ainda ha marcos essenciais sem fonte suficiente"
                    + (": " + "; ".join(labels) if labels else ".")
                ),
            )
        )
    testimony_gaps = _list_value(payloads.get("depoimentos", {}), "lacunas")
    if testimony_gaps:
        findings.append(
            ValidationFinding(
                severity="aviso",
                section="depoimentos",
                code="testimony_coverage_gaps",
                message=(
                    "A secao de depoimentos ainda registra fontes ou falas que precisam "
                    "ser localizadas."
                ),
            )
        )
    contradiction_items = _list_value(payloads.get("contradicoes", {}), "itens")
    contradiction_section = by_key.get("contradicoes")
    if (
        contradiction_section is not None
        and contradiction_section.status == "concluido"
        and not contradiction_items
    ):
        findings.append(
            ValidationFinding(
                severity="aviso",
                section="contradicoes",
                code="no_supported_contradiction",
                message=(
                    "Nenhuma contradicao potencial foi sustentada por dois trechos "
                    "literais; isso pode refletir ausencia de evidencia ou cobertura "
                    "insuficiente."
                ),
            )
        )


def _load_chunks(
    connection: sqlite3.Connection,
    processo_id: str,
) -> dict[tuple[int, int], sqlite3.Row]:
    rows = connection.execute(
        """
        SELECT page_number, chunk_index, text, document_type, source_confidence
        FROM chunks
        WHERE processo_id = ?
        """,
        (processo_id,),
    ).fetchall()
    return {(int(row["page_number"]), int(row["chunk_index"])): row for row in rows}


def _contains_excerpt(source_text: str, excerpt: str) -> bool:
    tokens = excerpt.strip().split()
    if not tokens:
        return False
    pattern = r"\s+".join(re.escape(token) for token in tokens)
    return re.search(pattern, source_text, flags=re.IGNORECASE) is not None


def _list_value(payload: dict[str, object], key: str) -> list[object]:
    value = payload.get(key, [])
    return value if isinstance(value, list) else []


def _int_value(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _invalid_item(section: str) -> ValidationFinding:
    return ValidationFinding(
        severity="erro",
        section=section,
        code="invalid_item",
        message="A secao contem um item fora do contrato esperado.",
    )


def _invalid_reference(section: str) -> ValidationFinding:
    return ValidationFinding(
        severity="erro",
        section=section,
        code="invalid_reference",
        message="A fonte do item esta fora do contrato esperado.",
    )


def _format_ms(value: int | None) -> str:
    return f"{value / 1000:.2f}s" if value is not None else "n/d"
