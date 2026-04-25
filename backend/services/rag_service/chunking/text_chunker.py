"""Simple text chunking for document ingestion."""

from __future__ import annotations

from services.rag_service.schemas import DocumentChunk, DocumentIngestRequest


class TextChunker:
    """Split text into overlapping word chunks."""

    def __init__(self, *, chunk_size: int = 120, chunk_overlap: int = 20) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap must be non-negative")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    def chunk_document(self, request: DocumentIngestRequest) -> list[DocumentChunk]:
        """Chunk a document ingest request into structured chunk records."""
        return chunk_text(
            document_id=request.document_id,
            source=request.source,
            text=request.text,
            metadata={
                **request.metadata,
                "title": request.title,
            },
            chunk_size=self._chunk_size,
            chunk_overlap=self._chunk_overlap,
        )


def chunk_text(
    *,
    document_id: str,
    source: str,
    text: str,
    metadata: dict,
    chunk_size: int = 120,
    chunk_overlap: int = 20,
) -> list[DocumentChunk]:
    """Split a document into overlapping word chunks."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must satisfy 0 <= overlap < chunk_size")

    normalized_text = " ".join(text.split())
    if not normalized_text:
        return []

    words = normalized_text.split(" ")
    step = chunk_size - chunk_overlap
    chunks: list[DocumentChunk] = []
    for chunk_index, start in enumerate(range(0, len(words), step), start=1):
        window = words[start : start + chunk_size]
        if not window:
            continue
        chunks.append(
            DocumentChunk(
                chunk_id=f"{document_id}-chunk-{chunk_index:04d}",
                document_id=document_id,
                text=" ".join(window),
                source=source,
                metadata={
                    **metadata,
                    "chunk_index": chunk_index,
                    "word_start": start,
                    "word_end": start + len(window),
                },
            )
        )
        if start + chunk_size >= len(words):
            break
    return chunks
