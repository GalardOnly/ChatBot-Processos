import pytest

from preparador_audiencia.embeddings import (
    DEFAULT_BERTIKAL_MODEL,
    DEFAULT_JURISBERT_MODEL,
    DEFAULT_LEGAL_BERTIMBAU_MODEL,
    HashEmbeddingProvider,
    resolve_embedding_device,
    resolve_embedding_spec,
)


def test_hash_embedding_normalizes_accents() -> None:
    provider = HashEmbeddingProvider(dimensions=32)

    with_accent = provider.embed_query("audi\u00eancia")
    without_accent = provider.embed_query("audiencia")

    assert with_accent == without_accent
    assert sum(value * value for value in with_accent) > 0


def test_hash_embedding_is_deterministic() -> None:
    provider = HashEmbeddingProvider(dimensions=32)

    first = provider.embed_query("medida protetiva urgente")
    second = provider.embed_query("medida protetiva urgente")

    assert first == second


def test_resolve_embedding_aliases_for_poc_models() -> None:
    assert resolve_embedding_spec("bertikal").model_name == DEFAULT_BERTIKAL_MODEL
    assert resolve_embedding_spec("jurisbert").model_name == DEFAULT_JURISBERT_MODEL
    assert resolve_embedding_spec("legal-bertimbau").model_name == DEFAULT_LEGAL_BERTIMBAU_MODEL
    assert resolve_embedding_spec("jurisbert").provider == "hf_mean_pool"


class _FakeCuda:
    def __init__(self, available: bool, devices: int = 1) -> None:
        self.available = available
        self.devices = devices

    def is_available(self) -> bool:
        return self.available

    def device_count(self) -> int:
        return self.devices


class _FakeTorch:
    def __init__(self, available: bool, devices: int = 1) -> None:
        self.cuda = _FakeCuda(available, devices)


def test_embedding_device_auto_prefers_cuda_and_falls_back_to_cpu() -> None:
    assert resolve_embedding_device(_FakeTorch(True), "auto") == "cuda"
    assert resolve_embedding_device(_FakeTorch(False), "auto") == "cpu"


def test_embedding_device_rejects_unavailable_cuda() -> None:
    with pytest.raises(RuntimeError, match="nao oferece CUDA"):
        resolve_embedding_device(_FakeTorch(False), "cuda")
