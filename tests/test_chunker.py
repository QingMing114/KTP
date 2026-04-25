"""Unit tests for the RAG text chunker."""

from __future__ import annotations

from services.rag_service.chunking.text_chunker import TextChunker
from services.rag_service.schemas import DocumentIngestRequest


def test_text_chunker_splits_text_with_overlap() -> None:
    chunker = TextChunker(chunk_size=5, chunk_overlap=2)
    request = DocumentIngestRequest(
        document_id="doc-001",
        title="Test Guide",
        source="local://test-guide",
        text="alpha beta gamma delta epsilon zeta eta theta iota kappa",
        metadata={"region": "henan"},
    )

    chunks = chunker.chunk_document(request)

    assert len(chunks) == 3
    assert chunks[0].chunk_id == "doc-001-chunk-0001"
    assert chunks[0].text == "alpha beta gamma delta epsilon"
    assert chunks[1].text == "delta epsilon zeta eta theta"
    assert chunks[2].text == "eta theta iota kappa"
    assert chunks[1].metadata["title"] == "Test Guide"
    assert chunks[1].metadata["region"] == "henan"
