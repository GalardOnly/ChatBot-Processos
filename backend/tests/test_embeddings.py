from preparador_audiencia.embeddings import (
    DEFAULT_BERTIKAL_MODEL,
    DEFAULT_JURISBERT_MODEL,
    DEFAULT_LEGAL_BERTIMBAU_MODEL,
    HashEmbeddingProvider,
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
