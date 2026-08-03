from preparador_audiencia.database import connect_database, initialize_database
from preparador_audiencia.hearing_dossier_repository import (
    DOSSIER_SECTION_KEYS,
    HearingDossierRepository,
)
from preparador_audiencia.repositories import ProcessoRepository


def _repository(tmp_path) -> HearingDossierRepository:
    connection = connect_database(tmp_path / "test.sqlite3")
    initialize_database(connection)
    ProcessoRepository(connection).create_pending(
        processo_id="proc_123",
        filename="processo.pdf",
        file_path="storage/processo.pdf",
        sha256_digest="abc",
    )
    return HearingDossierRepository(connection)


def test_repository_persists_each_section_and_marks_partial_result(tmp_path) -> None:
    repository = _repository(tmp_path)
    created = repository.prepare("proc_123")

    assert created.status == "pendente"
    assert tuple(section.key for section in created.sections) == DOSSIER_SECTION_KEYS

    repository.mark_section_processing("proc_123", "marcos_essenciais")
    repository.save_section(
        "proc_123",
        "marcos_essenciais",
        {"itens": [{"tipo": "data_fato"}], "avisos": []},
        model="gemini:test",
        fallback_used=False,
    )
    repository.mark_section_error("proc_123", "depoimentos", "servico indisponivel")

    result = repository.finish("proc_123")

    assert result.status == "parcial"
    events = next(section for section in result.sections if section.key == "marcos_essenciais")
    assert events.payload["itens"][0]["tipo"] == "data_fato"
    assert events.model == "gemini:test"


def test_repository_regeneration_resets_cached_sections(tmp_path) -> None:
    repository = _repository(tmp_path)
    repository.prepare("proc_123")
    repository.save_section(
        "proc_123",
        "marcos_essenciais",
        {"itens": [{"tipo": "data_fato"}]},
        model="gemini:test",
        fallback_used=False,
    )

    reset = repository.prepare("proc_123", regenerate=True)

    assert reset.status == "pendente"
    assert all(section.status == "pendente" for section in reset.sections)
    assert all(section.payload == {} for section in reset.sections)
