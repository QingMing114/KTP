"""Unit tests for the FAISS vector store wrapper."""

from __future__ import annotations

from pathlib import Path

from services.rag_service.embeddings.mock_embedding import MockEmbeddingProvider
from services.rag_service.schemas import DocumentChunk
from services.rag_service.vectorstore import FAISSVectorStore


def test_vectorstore_add_search_save_and_load(tmp_path: Path) -> None:
    vectorstore = FAISSVectorStore(str(tmp_path))
    embedder = MockEmbeddingProvider(dimension=64)
    chunks = [
        DocumentChunk(
            chunk_id="chunk-wheat",
            document_id="doc-wheat",
            text="Wheat health in Henan can be affected by drought stress.",
            source="local://wheat-guide",
            metadata={"crop_type": "wheat", "region": "henan"},
        ),
        DocumentChunk(
            chunk_id="chunk-maize",
            document_id="doc-maize",
            text="Maize field monitoring in Yunnan often focuses on disease spread.",
            source="local://maize-guide",
            metadata={"crop_type": "maize", "region": "yunnan"},
        ),
    ]

    vectorstore.add_chunks(chunks, embedder.embed_texts([chunk.text for chunk in chunks]))
    matches = vectorstore.search(
        embedder.embed_query("Wheat health in Henan can be affected by drought stress."),
        top_k=1,
    )

    assert len(matches) == 1
    assert matches[0].chunk_id == "chunk-wheat"

    vectorstore.save()

    reloaded = FAISSVectorStore(str(tmp_path))
    reloaded_matches = reloaded.search(
        embedder.embed_query("Maize field monitoring in Yunnan often focuses on disease spread."),
        top_k=1,
    )

    assert len(reloaded_matches) == 1
    assert reloaded_matches[0].chunk_id == "chunk-maize"
