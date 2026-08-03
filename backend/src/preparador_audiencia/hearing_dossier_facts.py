from __future__ import annotations

import re
from dataclasses import dataclass

from preparador_audiencia.search import SearchResult


@dataclass(frozen=True)
class DetectedKeyEvent:
    event_type: str
    label: str
    value: str
    description: str
    source: SearchResult


def detect_key_events(sources: list[SearchResult]) -> list[DetectedKeyEvent]:
    detected: list[DetectedKeyEvent] = []
    rules = (
        (
            "data_fato",
            "Data, horario e local do fato",
            re.compile(
                r"no\s+dia\s+(?P<value>\d{1,2}\s+de\s+[A-Za-zÀ-ÿ]+\s+de\s+"
                r"\d{4},\s*às?\s*\d{1,2}h(?:\d{2})?,\s*na\s+Rua\s+[^,]+,\s*"
                r"n[.º°]*\s*\d+,\s*Apto\.?\s*\d+,\s*Centro,\s*desta\s+Urbe)",
                re.IGNORECASE,
            ),
            "Data, horario e local descritos na narrativa dos fatos.",
            True,
        ),
        (
            "nascimento_reu",
            "Data de nascimento do reu",
            re.compile(
                r"nascid[oa]\s+aos?\s+(?P<value>\d{2}/\d{2}/\d{4})",
                re.IGNORECASE,
            ),
            "Data localizada na qualificacao da pessoa acusada.",
            True,
        ),
        (
            "recebimento_denuncia",
            "Recebimento da denuncia",
            re.compile(
                r"RECEBO\s+A\s+DEN[ÚU]NCIA.*?liberado\s+nos\s+autos\s+em\s+"
                r"(?P<value>\d{2}/\d{2}/\d{4})",
                re.IGNORECASE | re.DOTALL,
            ),
            "Data da decisao que recebeu a denuncia, conforme assinatura no sistema.",
            True,
        ),
        (
            "prisao",
            "Prisao em flagrante",
            re.compile(
                r"no\s+dia\s+(?P<value>\d{1,2}\s+de\s+[A-Za-zÀ-ÿ]+\s+de\s+"
                r"\d{4},\s*às?\s*\d{1,2}h).*?foi\s+preso\s+em\s+flagrante",
                re.IGNORECASE | re.DOTALL,
            ),
            "Data e horario associados a prisao em flagrante na narrativa acusatoria.",
            True,
        ),
        (
            "liberdade",
            "Liberdade provisoria",
            re.compile(
                r"(?P<value>concedida\s+a\s+liberdade\s+provis[óo]ria)",
                re.IGNORECASE,
            ),
            "A liberdade provisoria foi concedida mediante medidas cautelares.",
            True,
        ),
        (
            "liberdade",
            "Periodo das medidas cautelares",
            re.compile(
                r"Per[íi]odo\s+do\s+Cumprimento\s+da\s+Medida\s+"
                r"(?P<value>In[íi]cio:\s*\d{2}/\d{2}/\d{4}\s*-\s*"
                r"Fim:\s*\d{2}/\d{2}/\d{4})",
                re.IGNORECASE,
            ),
            "Periodo indicado no mandado de acompanhamento das cautelares.",
            True,
        ),
        (
            "audiencia",
            "Audiencia designada",
            re.compile(
                r"Data\s+e\s+hora\s+da\s+audi[êe]ncia:\s*"
                r"(?P<value>\d{2}/\d{2}/\d{4}\s+às?\s+\d{1,2}:\d{2}h)",
                re.IGNORECASE,
            ),
            "Data e horario indicados no expediente de audiencia.",
            False,
        ),
        (
            "audiencia",
            "Audiencia redesignada",
            re.compile(
                r"redesignando\s+a\s+audi[êe]ncia\s+para\s+o\s+dia\s+"
                r"(?P<value>\d{1,2}\s+de\s+[A-Za-zÀ-ÿ]+\s+de\s+\d{4},\s*"
                r"às?\s*\d{1,2}:\d{2}h)",
                re.IGNORECASE,
            ),
            "Nova data determinada no termo de audiencia.",
            False,
        ),
    )
    for event_type, label, pattern, description, first_only in rules:
        for source in sources:
            match = pattern.search(source.text)
            if match is None:
                continue
            detected.append(
                DetectedKeyEvent(
                    event_type=event_type,
                    label=label,
                    value=match.group("value"),
                    description=description,
                    source=source,
                )
            )
            if first_only:
                break
    return detected
