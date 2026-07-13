from preparador_audiencia.embeddings import HashEmbeddingProvider


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
