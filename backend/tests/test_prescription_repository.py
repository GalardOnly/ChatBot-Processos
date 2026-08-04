from preparador_audiencia.chunking import TextChunk
from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.prescription_repository import (
    PrescriptionCalculationRepository,
    prescription_calculation_identity,
)
from preparador_audiencia.repositories import ChunkRepository, ProcessoRepository


def _database_with_process(path):
    connection = connect_database(path)
    initialize_database(connection)
    ProcessoRepository(connection).create_pending(
        "proc-1",
        "processo.pdf",
        "storage/processo.pdf",
        "sha-1",
    )
    return connection


def test_saves_and_loads_reproducible_calculation(tmp_path) -> None:
    connection = _database_with_process(tmp_path / "test.sqlite3")
    repository = PrescriptionCalculationRepository(connection)
    input_payload = {"data_referencia": "2026-08-03", "delitos": [{"id": "d1"}]}
    result_payload = {"status": "prazos_nao_esgotados_no_calculo"}

    saved = repository.save(
        "proc-1",
        input_payload=input_payload,
        result_payload=result_payload,
    )
    loaded = repository.get(saved.id)

    assert saved.id == prescription_calculation_identity("proc-1", input_payload)
    assert loaded is not None
    assert loaded.input_payload == input_payload
    assert loaded.result_payload == result_payload
    connection.close()


def test_replacing_chunks_invalidates_prescription_calculations(tmp_path) -> None:
    connection = _database_with_process(tmp_path / "test.sqlite3")
    repository = PrescriptionCalculationRepository(connection)
    saved = repository.save(
        "proc-1",
        input_payload={"data_referencia": "2026-08-03", "delitos": [{"id": "d1"}]},
        result_payload={"status": "inconclusivo"},
    )

    ChunkRepository(connection).replace_for_processo(
        "proc-1",
        [TextChunk(page_number=1, chunk_index=0, text="novo texto")],
    )

    assert repository.get(saved.id) is None
    connection.close()
