from __future__ import annotations

import hashlib
import math
import os
import re
import unicodedata
from collections.abc import Iterable
from typing import Protocol

DEFAULT_BERTIKAL_MODEL = "felipemaiapolo/legalnlp-bert"
DEFAULT_HASH_DIMENSIONS = 384

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class EmbeddingProvider(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Gera embeddings para textos de documentos."""

    def embed_query(self, text: str) -> list[float]:
        """Gera embedding para a pergunta do usuario."""


def get_embedding_provider() -> EmbeddingProvider:
    provider_name = os.getenv("PREPARADOR_EMBEDDING_PROVIDER", "hash").strip().lower()
    if provider_name == "hash":
        return HashEmbeddingProvider()
    if provider_name == "bertikal":
        return BertikalEmbeddingProvider(
            model_name=os.getenv("PREPARADOR_EMBEDDING_MODEL", DEFAULT_BERTIKAL_MODEL)
        )
    raise ValueError(f"Provider de embedding desconhecido: {provider_name}")


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


class BertikalEmbeddingProvider:
    """Embeddings com BERTikal via mean pooling da ultima camada."""

    def __init__(self, model_name: str = DEFAULT_BERTIKAL_MODEL, max_length: int = 512) -> None:
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "Instale as dependencias opcionais com `python -m pip install -e .[bertikal]` "
                "para usar PREPARADOR_EMBEDDING_PROVIDER=bertikal."
            ) from exc

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


def _tokens(text: str) -> Iterable[str]:
    normalized = unicodedata.normalize("NFKD", text.lower())
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return TOKEN_PATTERN.findall(ascii_text)


def _mean_pool(token_embeddings, attention_mask, torch_module):
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    summed = torch_module.sum(token_embeddings * input_mask_expanded, dim=1)
    counts = torch_module.clamp(input_mask_expanded.sum(dim=1), min=1e-9)
    return summed / counts
