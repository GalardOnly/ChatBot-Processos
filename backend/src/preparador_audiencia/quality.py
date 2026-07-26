from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from preparador_audiencia.llm import llm_client_from_spec
from preparador_audiencia.search import SearchResult
from preparador_audiencia.settings import evaluator_llm_from_environment


@dataclass(frozen=True)
class LegalQualityEvaluation:
    evaluator_model: str
    fidelidade_fontes: int
    completude_juridica: int
    utilidade_audiencia: int
    risco_alucinacao: str
    pontos_fortes: list[str]
    problemas: list[str]
    faltou: list[str]
    veredito: str
    raw_response: str
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def evaluate_legal_quality(
    pergunta: str,
    resposta: str,
    sources: list[SearchResult],
    evaluator_model: str | None = None,
) -> LegalQualityEvaluation:
    model_spec = evaluator_model or evaluator_llm_from_environment()
    try:
        client = llm_client_from_spec(model_spec)
        llm_answer = client.complete(
            _quality_system_prompt(),
            _quality_user_prompt(pergunta, resposta, sources),
        )
    except Exception as exc:
        return _failed_evaluation(model_spec, str(exc))

    if llm_answer.error:
        return _failed_evaluation(llm_answer.model, llm_answer.error, llm_answer.answer)

    return parse_quality_evaluation(llm_answer.model, llm_answer.answer)


def parse_quality_evaluation(model: str, raw_response: str) -> LegalQualityEvaluation:
    try:
        payload = json.loads(_extract_json_object(raw_response))
    except Exception as exc:
        return _failed_evaluation(model, f"avaliador retornou JSON invalido: {exc}", raw_response)

    return LegalQualityEvaluation(
        evaluator_model=model,
        fidelidade_fontes=_score(payload.get("fidelidade_fontes")),
        completude_juridica=_score(payload.get("completude_juridica")),
        utilidade_audiencia=_score(payload.get("utilidade_audiencia")),
        risco_alucinacao=str(payload.get("risco_alucinacao") or "indefinido"),
        pontos_fortes=_string_list(payload.get("pontos_fortes")),
        problemas=_string_list(payload.get("problemas")),
        faltou=_string_list(payload.get("faltou")),
        veredito=str(payload.get("veredito") or "Avaliacao sem veredito."),
        raw_response=raw_response,
    )


def _quality_system_prompt() -> str:
    return (
        "Voce e um avaliador juridico auxiliar de uma PoC para preparacao de audiencia. "
        "Sua tarefa e avaliar se a resposta gerada esta fiel as fontes do processo, "
        "juridicamente completa para triagem inicial e util para audiencia. "
        "A resposta pode estar errada, incompleta ou contradizer as fontes. "
        "Procure ativamente contradicoes entre resposta e fontes antes de dar nota. "
        "Diferencas como conhecido versus nao conhecido, concedido versus negado, "
        "deferido versus indeferido, preso versus solto, ou datas divergentes sao erros graves. "
        "Se uma afirmacao central contradisser as fontes, fidelidade_fontes deve ser no maximo 2 "
        "e risco_alucinacao deve ser alto. "
        "Nao puna a resposta por apontar uma lacuna real. Se a resposta disser que uma data, "
        "documento ou calculo nao consta nas fontes, trate isso como conduta conservadora, "
        "nao como alucinacao. "
        "Diferencie afirmacao factual de ponto de conferencia. Um ponto marcado como "
        "'precisa confirmar' so deve ser penalizado se contradisser claramente as fontes. "
        "Nao decida o caso, nao invente fatos e nao use conhecimento externo para "
        "completar lacunas. "
        "Use apenas a pergunta, a resposta e as fontes fornecidas. "
        "Responda somente em JSON valido."
    )


def _quality_user_prompt(
    pergunta: str,
    resposta: str,
    sources: list[SearchResult],
) -> str:
    return "\n\n".join(
        [
            f"Pergunta original:\n{pergunta}",
            f"Resposta gerada:\n{resposta}",
            "Fontes recuperadas:",
            _sources_block(sources),
            "Avalie com notas inteiras de 1 a 5.",
            (
                "Retorne exatamente este formato JSON: "
                '{"fidelidade_fontes": 1, "completude_juridica": 1, '
                '"utilidade_audiencia": 1, "risco_alucinacao": "baixo|medio|alto", '
                '"pontos_fortes": [], "problemas": [], "faltou": [], "veredito": ""}'
            ),
        ]
    )


def _sources_block(sources: list[SearchResult]) -> str:
    if not sources:
        return "Nenhuma fonte recuperada."
    blocks = []
    for index, source in enumerate(sources, start=1):
        blocks.append(
            "\n".join(
                [
                    f"Fonte {index}",
                    f"Pagina: {source.page_number}",
                    f"Chunk: {source.chunk_index}",
                    f"Trecho: {source.text}",
                ]
            )
        )
    return "\n\n".join(blocks)


def _extract_json_object(text: str) -> str:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
    if fenced:
        return fenced.group(1)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("objeto JSON nao encontrado")
    return stripped[start : end + 1]


def _score(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 1
    return max(1, min(5, parsed))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _failed_evaluation(
    model: str,
    error: str,
    raw_response: str = "",
) -> LegalQualityEvaluation:
    return LegalQualityEvaluation(
        evaluator_model=model,
        fidelidade_fontes=1,
        completude_juridica=1,
        utilidade_audiencia=1,
        risco_alucinacao="indefinido",
        pontos_fortes=[],
        problemas=[],
        faltou=[],
        veredito="Nao foi possivel avaliar a qualidade juridica automaticamente.",
        raw_response=raw_response,
        error=error,
    )
