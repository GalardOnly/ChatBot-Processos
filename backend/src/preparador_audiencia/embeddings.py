from __future__ import annotations

import hashlib
import math
import os
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

DEFAULT_BERTIKAL_MODEL = "felipemaiapolo/legalnlp-bert"
DEFAULT_JURISBERT_MODEL = "alfaneo/jurisbert-base-portuguese-uncased"
DEFAULT_LEGAL_BERTIMBAU_MODEL = "rufimelo/Legal-BERTimbau-sts-base"
DEFAULT_HASH_DIMENSIONS = 384

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class ResolvedEmbeddingSpec:
    provider: str
    model_name: str | None
    label: str


class EmbeddingProvider(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Gera embeddings para textos de documentos."""

    def embed_query(self, text: str) -> list[float]:
        """Gera embedding para a pergunta do usuario."""


def get_embedding_provider() -> EmbeddingProvider:
    provider_name = os.getenv("PREPARADOR_EMBEDDING_PROVIDER", "hash").strip()
    model_name = os.getenv("PREPARADOR_EMBEDDING_MODEL")
    if model_name and provider_name.lower() in {"bertikal", "hf", "hf_mean_pool"}:
        return embedding_provider_from_spec(f"{provider_name}:{model_name}")
    return embedding_provider_from_spec(provider_name)


def embedding_provider_from_spec(spec: str) -> EmbeddingProvider:
    resolved = resolve_embedding_spec(spec)
    if resolved.provider == "hash":
        return HashEmbeddingProvider()
    if resolved.provider == "hf_mean_pool" and resolved.model_name:
        return MeanPoolingTransformerEmbeddingProvider(resolved.model_name)
    if resolved.provider == "sentence_transformers" and resolved.model_name:
        return SentenceTransformersEmbeddingProvider(resolved.model_name)
    raise ValueError(f"Provider de embedding desconhecido: {spec}")


def resolve_embedding_spec(spec: str) -> ResolvedEmbeddingSpec:
    provider_name, _, model_name = spec.strip().partition(":")
    provider_key = provider_name.lower().replace("_", "-")
    if provider_key == "hash":
        return ResolvedEmbeddingSpec("hash", None, "hash")
    if provider_key == "bertikal":
        return ResolvedEmbeddingSpec(
            "hf_mean_pool",
            model_name or DEFAULT_BERTIKAL_MODEL,
            "BERTikal",
        )
    if provider_key == "jurisbert":
        return ResolvedEmbeddingSpec(
            "hf_mean_pool",
            model_name or DEFAULT_JURISBERT_MODEL,
            "JurisBERT",
        )
    if provider_key == "legal-bertimbau":
        return ResolvedEmbeddingSpec(
            "sentence_transformers",
            model_name or DEFAULT_LEGAL_BERTIMBAU_MODEL,
            "Legal-BERTimbau",
        )
    if provider_key in {"hf", "hf-mean-pool"} and model_name:
        return ResolvedEmbeddingSpec("hf_mean_pool", model_name, model_name)
    if provider_key in {"st", "sentence-transformers"} and model_name:
        return ResolvedEmbeddingSpec("sentence_transformers", model_name, model_name)
    raise ValueError(f"Provider de embedding desconhecido: {spec}")


class HashEmbeddingProvider:
    """Provider leve para desenvolvimento e testes, baseado em tokens normalizados."""

    def __init__(self, dimensions: int = DEFAULT_HASH_DIMENSIONS) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions deve ser positivo")
        self.dimensions = dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class MeanPoolingTransformerEmbeddingProvider:
    """Embeddings Hugging Face via mean pooling da ultima camada."""

    def __init__(self, model_name: str = DEFAULT_BERTIKAL_MODEL, max_length: int = 512) -> None:
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "Instale as dependencias opcionais com `python -m pip install -e .[bertikal]` "
                "para usar modelos Hugging Face locais."
            ) from exc

        self.model_name = model_name
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name)
        self.model.eval()
        self.max_length = max_length

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        encoded = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        )
        with self.torch.no_grad():
            output = self.model(**encoded)
        pooled = _mean_pool(
            token_embeddings=output.last_hidden_state,
            attention_mask=encoded["attention_mask"],
            torch_module=self.torch,
        )
        normalized = self.torch.nn.functional.normalize(pooled, p=2, dim=1)
        return normalized.cpu().tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]


BertikalEmbeddingProvider = MeanPoolingTransformerEmbeddingProvider


class SentenceTransformersEmbeddingProvider:
    """Embeddings com modelos sentence-transformers."""

    def __init__(self, model_name: str) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Instale as dependencias opcionais com `python -m pip install -e .[models]` "
                "para usar JurisBERT ou Legal-BERTimbau."
            ) from exc

        self.model_name = model_name
        self.model = SentenceTransformer(model_name)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        embeddings = self.model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]


def _tokens(text: str) -> Iterable[str]:
    normalized = unicodedata.normalize("NFKD", text.lower())
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return TOKEN_PATTERN.findall(ascii_text)


def _mean_pool(token_embeddings, attention_mask, torch_module):
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    summed = torch_module.sum(token_embeddings * input_mask_expanded, dim=1)
    counts = torch_module.clamp(input_mask_expanded.sum(dim=1), min=1e-9)
    return summed / counts
