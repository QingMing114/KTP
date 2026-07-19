"""Persistent metadata store for ingested RAG documents and chunks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from services.rag_service.schemas import DocumentChunk, DocumentIngestRequest


class DocumentStore:
    """Persist ingested document and chunk metadata to local JSON storage."""

    def __init__(self, vectorstore_dir: str) -> None:
        self._root_dir = Path(vectorstore_dir)
        self._store_path = self._root_dir / "documents.json"
        self._documents: dict[str, dict[str, Any]] = {}
        self._chunks: dict[str, dict[str, Any]] = {}
        self.load()

    @property
    def document_count(self) -> int:
        return len(self._documents)

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    def has_document(self, document_id: str) -> bool:
        """Return whether the document has already been ingested."""
        return document_id in self._documents

    def add_document(
        self,
        request: DocumentIngestRequest,
        chunks: list[DocumentChunk],
    ) -> None:
        """Persist a newly ingested document and its chunks."""
        if self.has_document(request.document_id):
            raise ValueError(f"document_id {request.document_id} already exists")

        self._documents[request.document_id] = {
            "document_id": request.document_id,
            "title": request.title,
            "source": request.source,
            "metadata": request.metadata,
            "chunk_ids": [chunk.chunk_id for chunk in chunks],
        }
        for chunk in chunks:
            self._chunks[chunk.chunk_id] = chunk.model_dump()

    def get_chunk(self, chunk_id: str) -> DocumentChunk | None:
        """Return a single chunk by id."""
        payload = self._chunks.get(chunk_id)
        if payload is None:
            return None
        return DocumentChunk.model_validate(payload)

    def get_chunks(self, chunk_ids: list[str]) -> list[DocumentChunk]:
        """Return chunks in the requested order."""
        return [
            chunk
            for chunk_id in chunk_ids
            if (chunk := self.get_chunk(chunk_id)) is not None
        ]

    def list_documents(self) -> list[dict[str, Any]]:
        """Return metadata for all ingested documents."""
        results: list[dict[str, Any]] = []
        for doc_id, doc in self._documents.items():
            results.append({
                "document_id": doc.get("document_id", doc_id),
                "title": doc.get("title", ""),
                "source": doc.get("source", ""),
                "metadata": doc.get("metadata", {}),
                "chunk_count": len(doc.get("chunk_ids", [])),
            })
        return results

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        """Return metadata for a single document, or None if not found."""
        doc = self._documents.get(document_id)
        if doc is None:
            return None
        return {
            "document_id": doc.get("document_id", document_id),
            "title": doc.get("title", ""),
            "source": doc.get("source", ""),
            "metadata": doc.get("metadata", {}),
            "chunk_ids": doc.get("chunk_ids", []),
            "chunk_count": len(doc.get("chunk_ids", [])),
        }

    def delete_document(self, document_id: str) -> bool:
        """Remove a document and its chunks. Returns True if found and deleted."""
        doc = self._documents.pop(document_id, None)
        if doc is None:
            return False
        for chunk_id in doc.get("chunk_ids", []):
            self._chunks.pop(chunk_id, None)
        return True

    def save(self) -> None:
        """Persist documents and chunks to disk."""
        self._root_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "documents": self._documents,
            "chunks": self._chunks,
        }
        self._store_path.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def load(self) -> None:
        """Load documents and chunks from disk if available."""
        if not self._store_path.exists():
            self._documents = {}
            self._chunks = {}
            return
        payload = json.loads(self._store_path.read_text(encoding="utf-8"))
        self._documents = dict(payload.get("documents", {}))
        self._chunks = dict(payload.get("chunks", {}))
