from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_QUESTION_SOURCE_PATH = Path(__file__).resolve().parents[2] / "data/question_sources.json"

QUESTION_PATTERNS = [
    {
        "suffix": "localizar",
        "objective": "Localizar informacoes relevantes no processo.",
        "template": (
            "Ao analisar o processo, quais informacoes sobre {topic} aparecem nos autos, "
            "em quais paginas estao e o que elas significam para a audiencia?"
        ),
    },
    {
        "suffix": "confirmar",
        "objective": "Transformar o tema em pontos de conferencia.",
        "template": (
            "Quais fatos, datas, documentos ou lacunas sobre {topic} precisam ser "
            "confirmados antes ou durante a audiencia? Cite as paginas de apoio."
        ),
    },
    {
        "suffix": "perguntar",
        "objective": "Gerar perguntas praticas para a audiencia.",
        "template": (
            "Quais perguntas o defensor deve fazer sobre {topic}, para quem elas devem "
            "ser dirigidas e qual trecho do processo justifica cada pergunta?"
        ),
    },
]


@dataclass(frozen=True)
class QuestionSource:
    id: str
    title: str
    url: str
    kind: str
    official: bool
    area: str
    audiencia: str
    license_note: str
    topics: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class QuestionCandidate:
    id: str
    titulo: str
    area: str
    audiencia: str
    objetivo: str
    pergunta: str
    quando_usar: str
    tags: list[str]
    prioridade: int
    status: str
    source_id: str
    source_title: str
    source_url: str
    source_kind: str
    official_source: bool
    license_note: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def load_question_sources(path: str | Path = DEFAULT_QUESTION_SOURCE_PATH) -> list[QuestionSource]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        QuestionSource(
            id=str(item["id"]),
            title=str(item["title"]),
            url=str(item["url"]),
            kind=str(item["kind"]),
            official=bool(item["official"]),
            area=str(item["area"]),
            audiencia=str(item["audiencia"]),
            license_note=str(item["license_note"]),
            topics=[str(topic) for topic in item.get("topics", [])],
        )
        for item in payload.get("sources", [])
    ]


def generate_question_candidates(
    sources: list[QuestionSource],
    *,
    area: str | None = None,
    audiencia: str | None = None,
    source_kind: str | None = None,
    official_only: bool = False,
    include_benchmark: bool = False,
    limit: int | None = None,
) -> list[QuestionCandidate]:
    selected = [
        source
        for source in sources
        if _matches_source(
            source,
            area=area,
            audiencia=audiencia,
            source_kind=source_kind,
            official_only=official_only,
            include_benchmark=include_benchmark,
        )
    ]
    candidates = [
        _candidate_from_topic(source, topic, pattern)
        for source in selected
        for topic in source.topics
        for pattern in QUESTION_PATTERNS
    ]
    candidates = sorted(candidates, key=lambda item: (item.prioridade, item.area, item.id))
    return candidates[:limit] if limit is not None else candidates


def question_candidates_to_cases(candidates: list[QuestionCandidate]) -> dict[str, object]:
    return {
        "source_id": "perguntas-candidatas-curadas-v0.1",
        "document": "processo_do_usuario.pdf",
        "cases": [
            {
                "id": candidate.id,
                "pergunta": candidate.pergunta,
                "expected_pages": [],
                "expected_terms": [],
            }
            for candidate in candidates
        ],
    }


def write_question_candidates(
    candidates: list[QuestionCandidate],
    output_path: str | Path,
    *,
    output_format: str,
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "json":
        path.write_text(
            json.dumps(
                [candidate.to_dict() for candidate in candidates],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return
    if output_format == "cases-json":
        path.write_text(
            json.dumps(question_candidates_to_cases(candidates), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return
    path.write_text(render_question_candidates_markdown(candidates), encoding="utf-8")


def render_question_candidates_markdown(candidates: list[QuestionCandidate]) -> str:
    lines = [
        "# Perguntas Candidatas para Audiencia",
        "",
        "Perguntas geradas a partir de fontes curadas. Revisar antes de promover ao banco oficial.",
        "",
        f"Total: {len(candidates)}",
        "",
    ]
    current_group = None
    for candidate in candidates:
        group = f"{candidate.area} / {candidate.audiencia}"
        if group != current_group:
            lines.extend([f"## {group}", ""])
            current_group = group
        lines.extend(
            [
                f"### {candidate.titulo}",
                "",
                f"Status: `{candidate.status}`",
                "",
                f"Objetivo: {candidate.objetivo}",
                "",
                f"Pergunta: {candidate.pergunta}",
                "",
                f"Fonte: [{candidate.source_title}]({candidate.source_url})",
                "",
                f"Licenca/uso: {candidate.license_note}",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def _matches_source(
    source: QuestionSource,
    *,
    area: str | None,
    audiencia: str | None,
    source_kind: str | None,
    official_only: bool,
    include_benchmark: bool,
) -> bool:
    if area and source.area != area:
        return False
    if audiencia and source.audiencia != audiencia:
        return False
    if source_kind and source.kind != source_kind:
        return False
    if official_only and not source.official:
        return False
    return include_benchmark or source.area != "benchmark"


def _candidate_from_topic(
    source: QuestionSource,
    topic: str,
    pattern: dict[str, str],
) -> QuestionCandidate:
    topic_slug = _slug(topic)
    suffix = pattern["suffix"]
    return QuestionCandidate(
        id=f"cand_{source.id}_{topic_slug}_{suffix}",
        titulo=f"{_title(topic)} - {pattern['objective']}",
        area=source.area,
        audiencia=source.audiencia,
        objetivo=pattern["objective"],
        pergunta=pattern["template"].format(topic=topic),
        quando_usar=_when_to_use(source),
        tags=_tags(source, topic),
        prioridade=_priority(source),
        status="candidate",
        source_id=source.id,
        source_title=source.title,
        source_url=source.url,
        source_kind=source.kind,
        official_source=source.official,
        license_note=source.license_note,
    )


def _when_to_use(source: QuestionSource) -> str:
    if source.audiencia == "avaliacao":
        return "Benchmark tecnico, comparacao de modelos ou avaliacao de recuperacao."
    if source.audiencia == "qualquer":
        return "Triagem inicial, revisao rapida ou preparacao geral do processo."
    return f"Preparacao de audiencia de {source.audiencia}."


def _priority(source: QuestionSource) -> int:
    if source.official and source.audiencia != "avaliacao":
        return 1
    if source.official:
        return 2
    return 3


def _tags(source: QuestionSource, topic: str) -> list[str]:
    tags = {source.area, source.audiencia, source.kind}
    tags.update(_slug(part) for part in topic.split() if len(part) > 3)
    return sorted(tag for tag in tags if tag and tag != "qualquer")


def _title(text: str) -> str:
    return " ".join(part.capitalize() for part in text.split())


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
    return slug or "tema"
