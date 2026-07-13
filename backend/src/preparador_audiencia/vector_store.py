from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from preparador_audiencia.repositories import ChunkRecord
from preparador_audiencia.settings import chroma_dir_from_environment

COLLECTION_NAME = "processo_chunks"


@dataclass(frozen=True)
class VectorSearchResult:
    vector_id: str
    text: str
    page_number: int
    chunk_index: int
    document_type: str | None
    distance: float
    score: float


class ChromaVectorStore:
    def __init__(self, path: Path | None = None, collection_name: str = COLLECTION_NAME) -> None:
        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError(
                "ChromaDB nao esta instalado. Rode `python -m pip install -e .` no backend."
            ) from exc

        resolved_path = path or chroma_dir_from_environment()
        resolved_path.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
        self.client = chromadb.PersistentClient(path=str(resolved_path))
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def replace_process_chunks(
        self,
        processo_id: str,
        chunks: list[ChunkRecord],
        embeddings: list[list[float]],
    ) -> dict[int, str]:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks e embeddings devem ter o mesmo tamanho")

        self.delete_process(processo_id)
        if not chunks:
            return {}

        ids = [_vector_id_for_chunk(chunk) for chunk in chunks]
        self.collection.add(
            ids=ids,
            documents=[chunk.text for chunk in chunks],
            metadatas=[_metadata_for_chunk(processo_id, chunk) for chunk in chunks],
            embeddings=embeddings,
        )
        return {chunk.id: vector_id for chunk, vector_id in zip(chunks, ids, strict=True)}

    def delete_process(self, processo_id: str) -> None:
        existing = self.collection.get(where={"processo_id": processo_id})
        ids = existing.get("ids", [])
        if ids:
            self.collection.delete(ids=ids)

    def search(
        self,
        processo_id: str,
        query_embedding: list[float],
        top_k: int,
    ) -> list[VectorSearchResult]:
        if top_k <= 0:
            raise ValueError("top_k deve ser positivo")

        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where={"processo_id": processo_id},
            include=["documents", "metadatas", "distances"],
        )
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        hits: list[VectorSearchResult] = []
        for vector_id, document, metadata, distance in zip(
            ids, documents, metadatas, distances, strict=False
        ):
            typed_metadata = metadata or {}
            distance_value = float(distance)
            hits.append(
                VectorSearchResult(
                    vector_id=str(vector_id),
                    text=str(document),
                    page_number=int(typed_metadata["page_number"]),
                    chunk_index=int(typed_metadata["chunk_index"]),
                    document_type=_optional_text(typed_metadata.get("document_type")),
                    distance=distance_value,
                    score=max(0.0, min(1.0, 1.0 - distance_value)),
                )
            )
        return hits


def _vector_id_for_chunk(chunk: ChunkRecord) -> str:
    return f"{chunk.processo_id}-p{chunk.page_number:04d}-c{chunk.chunk_index:04d}"


def _metadata_for_chunk(processo_id: str, chunk: ChunkRecord) -> dict[str, Any]:
    return {
        "processo_id": processo_id,
        "page_number": chunk.page_number,
        "chunk_index": chunk.chunk_index,
        "document_type": chunk.document_type or "",
    }


def _optional_text(value: object) -> str | None:
    text = str(value or "")
    return text or None


def safe_collection_name(prefix: str, value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_")
    name = f"{prefix}_{cleaned}"[:63].strip("_")
    if len(name) < 3:
        return f"{prefix}_default"
    return name
