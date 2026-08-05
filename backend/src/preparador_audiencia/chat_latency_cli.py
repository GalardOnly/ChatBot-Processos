from __future__ import annotations

import argparse

from preparador_audiencia.chat_latency import (
    profile_chat_latency,
    write_chat_latency_report,
)
from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.environment import load_environment
from preparador_audiencia.repositories import ProcessoRepository
from preparador_audiencia.settings import primary_llm_from_environment


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mede separadamente carga dos embeddings, recuperacao e Gemini."
    )
    parser.add_argument("--processo-id", required=True)
    parser.add_argument("--pergunta", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--repeticoes", type=int, default=3)
    parser.add_argument("--embedding")
    parser.add_argument("--with-gemini", action="store_true")
    parser.add_argument("--gemini-model")
    parser.add_argument("--max-llm-calls", type=int, default=0)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument(
        "--output",
        default="reports/perfil-latencia-chat.json",
    )
    args = parser.parse_args()

    if args.top_k <= 0:
        parser.error("--top-k deve ser maior que zero.")
    if args.repeticoes <= 0:
        parser.error("--repeticoes deve ser maior que zero.")
    if args.with_gemini and args.max_llm_calls < 1:
        parser.error("Use --max-llm-calls 1 para autorizar uma chamada ao Gemini.")

    load_environment(args.env_file)
    _validate_process(args.processo_id, parser)
    llm_model = None
    if args.with_gemini:
        llm_model = args.gemini_model or primary_llm_from_environment()
        if not llm_model.startswith("gemini:"):
            parser.error("O perfil desta etapa aceita apenas um modelo Gemini.")

    report = profile_chat_latency(
        processo_id=args.processo_id,
        pergunta=args.pergunta,
        top_k=args.top_k,
        repetitions=args.repeticoes,
        embedding_spec=args.embedding,
        llm_model=llm_model,
        max_llm_calls=args.max_llm_calls,
    )
    output = write_chat_latency_report(report, args.output)
    _print_report(report)
    print(f"Relatorio: {output}")


def _validate_process(processo_id: str, parser: argparse.ArgumentParser) -> None:
    connection = connect_database()
    initialize_database(connection)
    try:
        process = ProcessoRepository(connection).get(processo_id)
    finally:
        connection.close()
    if process is None:
        parser.error(f"Processo nao encontrado: {processo_id}")
    if process.status != "concluido":
        parser.error(
            f"O processo precisa estar concluido; status atual: {process.status}."
        )


def _print_report(report) -> None:
    print(
        "Runtime de embeddings "
        f"({report.runtime_embedding.dispositivo}): "
        f"{report.runtime_embedding.inicializacao_ms} ms"
    )
    print("Carga dos modelos de embedding")
    for timing in report.modelos_embedding:
        print(
            f"  {timing.rotulo} ({timing.dispositivo}): "
            f"carga {timing.carregamento_ms} ms; "
            f"primeiro embedding {timing.primeiro_embedding_ms} ms"
        )
    print("Recuperacao")
    for timing in report.recuperacoes:
        print(
            f"  execucao {timing.execucao}: {timing.latencia_ms} ms; "
            f"{timing.fontes_recuperadas} fontes"
        )
    if report.chamada_llm is None:
        print("Gemini: nao chamado")
    else:
        print(
            f"Gemini: {report.chamada_llm.chamada_total_ms} ms "
            f"({report.chamada_llm.modelo})"
        )
        if report.chamada_llm.erro:
            print(f"Erro do Gemini: {report.chamada_llm.erro}")
    print(
        "Resumo: carga de embeddings "
        f"{report.resumo.carga_embeddings_ms} ms; recuperacao quente mediana "
        f"{report.resumo.recuperacao_quente_mediana_ms} ms"
    )


if __name__ == "__main__":
    main()
