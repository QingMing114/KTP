"""FAISS vector store wrapper for chunk embeddings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import faiss
import numpy as np

from services.rag_service.schemas import DocumentChunk


@dataclass(slots=True)
class SearchMatch:
    """Search match returned by the vector store."""

    chunk_id: str
    score: float


class FAISSVectorStore:
    """Persist chunk embeddings and perform similarity search with FAISS."""

    def __init__(self, vectorstore_dir: str) -> None:
        self._root_dir = Path(vectorstore_dir)
        self._index_path = self._root_dir / "chunks.faiss"
        self._mapping_path = self._root_dir / "chunk_ids.json"
        self._chunk_ids: list[str] = []
        self._index: faiss.IndexFlatIP | None = None
        self.load()

    @property
    def count(self) -> int:
        """Return the number of indexed chunk vectors."""
        return len(self._chunk_ids)

    def add_chunks(self, chunks: list[DocumentChunk], embeddings: np.ndarray) -> None:
        """Add chunk embeddings to the FAISS index."""
        normalized_embeddings = np.asarray(embeddings, dtype=np.float32)
        if normalized_embeddings.ndim != 2:
            raise ValueError("embeddings must be a 2D array")
        if len(chunks) != normalized_embeddings.shape[0]:
            raise ValueError("chunks and embeddings must have the same length")
        if not chunks:
            return

        normalized_embeddings = self._normalize_rows(normalized_embeddings)
        self._ensure_index(normalized_embeddings.shape[1])
        if self._index is None:
            raise ValueError("FAISS index is not initialized")

        self._index.add(normalized_embeddings)
        self._chunk_ids.extend(chunk.chunk_id for chunk in chunks)

    def search(self, query_embedding: np.ndarray, top_k: int) -> list[SearchMatch]:
        """Return top-k matches from the FAISS index."""
        if top_k <= 0 or self._index is None or self.count == 0:
            return []

        query = np.asarray(query_embedding, dtype=np.float32).reshape(1, -1)
        query = self._normalize_rows(query)
        if query.shape[1] != self._index.d:
            raise ValueError(
                f"query embedding dimension {query.shape[1]} does not match index dimension {self._index.d}"
            )

        scores, indices = self._index.search(query, min(top_k, self.count))
        matches: list[SearchMatch] = []
        for score, index in zip(scores[0].tolist(), indices[0].tolist()):
            if index < 0:
                continue
            matches.append(
                SearchMatch(
                    chunk_id=self._chunk_ids[index],
                    score=float(score),
                )
            )
        return matches

    def save(self) -> None:
        """Persist the FAISS index and chunk-id mapping."""
        self._root_dir.mkdir(parents=True, exist_ok=True)
        if self._index is not None and self.count > 0:
            faiss.write_index(self._index, str(self._index_path))
        elif self._index_path.exists():
            self._index_path.unlink()

        self._mapping_path.write_text(
            json.dumps({"chunk_ids": self._chunk_ids}, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

    def load(self) -> None:
        """Load the FAISS index and chunk-id mapping if they exist."""
        if self._mapping_path.exists():
            mapping_payload = json.loads(self._mapping_path.read_text(encoding="utf-8"))
            self._chunk_ids = list(mapping_payload.get("chunk_ids", []))
        else:
            self._chunk_ids = []

        if self._index_path.exists():
            self._index = faiss.read_index(str(self._index_path))
        else:
            self._index = None

    def _ensure_index(self, dimension: int) -> None:
        if self._index is None:
            self._index = faiss.IndexFlatIP(dimension)
            return
        if self._index.d != dimension:
            raise ValueError(
                f"embedding dimension {dimension} does not match existing index dimension {self._index.d}"
            )

    @staticmethod
    def _normalize_rows(matrix: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        safe_norms = np.where(norms == 0.0, 1.0, norms)
        return matrix / safe_norms
