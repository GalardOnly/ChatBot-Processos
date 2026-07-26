from preparador_audiencia.chunking import TextChunk
from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.quality import LegalQualityEvaluation
from preparador_audiencia.repositories import (
    ChunkRepository,
    ProcessoRepository,
    QualityEvaluationRepository,
)


def test_process_repository_lifecycle(tmp_path) -> None:
    connection = connect_database(tmp_path / "test.sqlite3")
    initialize_database(connection)
    processos = ProcessoRepository(connection)

    created = processos.create_pending(
        processo_id="proc_123",
        filename="processo.pdf",
        file_path="storage/processo.pdf",
        sha256_digest="abc",
    )
    assert created.status == "pendente"

    processos.mark_processing("proc_123")
    processing = processos.get("proc_123")
    assert processing.status == "processando"
    assert processing.progress_stage == "iniciando"

    processos.update_progress(
        "proc_123",
        stage="extraindo",
        current=1,
        total=2,
        message="Extraindo pagina 1 de 2",
        page_count=1,
    )
    progress = processos.get("proc_123")
    assert progress.progress_current == 1
    assert progress.progress_total == 2
    assert progress.page_count == 1

    processos.mark_completed("proc_123", page_count=2, chunk_count=5)
    completed = processos.get("proc_123")
    assert completed.status == "concluido"
    assert completed.progress_stage == "concluido"
    assert completed.page_count == 2
    assert completed.chunk_count == 5


def test_process_repository_prefers_completed_duplicate(tmp_path) -> None:
    connection = connect_database(tmp_path / "test.sqlite3")
    initialize_database(connection)
    processos = ProcessoRepository(connection)
    processos.create_pending("proc_pending", "a.pdf", "a.pdf", "same")
    processos.create_pending("proc_completed", "b.pdf", "b.pdf", "same")
    processos.mark_completed("proc_completed", page_count=2, chunk_count=3)

    reusable = processos.find_reusable_by_sha256("same")

    assert reusable is not None
    assert reusable.id == "proc_completed"


def test_chunk_repository_replaces_chunks(tmp_path) -> None:
    connection = connect_database(tmp_path / "test.sqlite3")
    initialize_database(connection)
    ProcessoRepository(connection).create_pending(
        processo_id="proc_123",
        filename="processo.pdf",
        file_path="storage/processo.pdf",
        sha256_digest="abc",
    )
    chunks = ChunkRepository(connection)

    chunks.replace_for_processo(
        "proc_123",
        [
            TextChunk(page_number=1, chunk_index=0, text="A", document_type=None),
            TextChunk(page_number=1, chunk_index=1, text="B", document_type="edital"),
        ],
    )
    assert chunks.count_for_processo("proc_123") == 2

    chunks.replace_for_processo(
        "proc_123",
        [TextChunk(page_number=2, chunk_index=0, text="C", document_type=None)],
    )
    assert chunks.count_for_processo("proc_123") == 1


def test_quality_evaluation_repository_persists_evaluation(tmp_path) -> None:
    connection = connect_database(tmp_path / "test.sqlite3")
    initialize_database(connection)
    ProcessoRepository(connection).create_pending(
        processo_id="proc_123",
        filename="processo.pdf",
        file_path="storage/processo.pdf",
        sha256_digest="abc",
    )
    evaluation = LegalQualityEvaluation(
        evaluator_model="groq:judge",
        fidelidade_fontes=5,
        completude_juridica=4,
        utilidade_audiencia=4,
        risco_alucinacao="baixo",
        pontos_fortes=["cita fonte"],
        problemas=[],
        faltou=["perguntas"],
        veredito="Boa para triagem.",
        raw_response="{}",
    )

    QualityEvaluationRepository(connection).add(
        processo_id="proc_123",
        pergunta="Existe audiencia?",
        resposta="Sim [p. 1].",
        evaluation=evaluation,
        generator_model="gemini:flash",
    )

    row = connection.execute("SELECT * FROM quality_evaluations").fetchone()
    assert row["evaluator_model"] == "groq:judge"
    assert row["generator_model"] == "gemini:flash"
    assert row["fidelidade_fontes"] == 5
