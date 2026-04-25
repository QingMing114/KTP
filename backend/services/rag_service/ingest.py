"""Document ingestion pipeline for the RAG service."""

from __future__ import annotations

from services.rag_service.chunking.text_chunker import TextChunker
from services.rag_service.embeddings.base import BaseEmbeddingProvider
from services.rag_service.schemas import DocumentIngestRequest, DocumentIngestResponse
from services.rag_service.storage.document_store import DocumentStore
from services.rag_service.vectorstore import FAISSVectorStore


class DocumentIngester:
    """Ingest documents into the chunk store and FAISS index."""

    def __init__(
        self,
        *,
        chunker: TextChunker,
        embedding_provider: BaseEmbeddingProvider,
        vectorstore: FAISSVectorStore,
        document_store: DocumentStore,
    ) -> None:
        self._chunker = chunker
        self._embedding_provider = embedding_provider
        self._vectorstore = vectorstore
        self._document_store = document_store

    def ingest(self, request: DocumentIngestRequest) -> DocumentIngestResponse:
        """Chunk, embed, and persist a document."""
        if self._document_store.has_document(request.document_id):
            raise ValueError(f"document_id {request.document_id} already exists")

        chunks = self._chunker.chunk_document(request)
        if not chunks:
            raise ValueError("document text produced no chunks")

        embeddings = self._embedding_provider.embed_texts([chunk.text for chunk in chunks])
        self._vectorstore.add_chunks(chunks, embeddings)
        self._document_store.add_document(request, chunks)
        self._vectorstore.save()
        self._document_store.save()
        return DocumentIngestResponse(
            document_id=request.document_id,
            chunk_count=len(chunks),
            success=True,
            message="document ingested",
        )
