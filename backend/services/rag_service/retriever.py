"""Retrieval pipeline for the RAG service."""

from __future__ import annotations

from services.rag_service.embeddings.base import BaseEmbeddingProvider
from services.rag_service.reranker import BasicReranker
from services.rag_service.schemas import RAGQueryRequest, RetrievedChunk
from services.rag_service.storage.document_store import DocumentStore
from services.rag_service.vectorstore import FAISSVectorStore


class Retriever:
    """Retrieve and rerank knowledge chunks for a structured RAG query."""

    def __init__(
        self,
        *,
        embedding_provider: BaseEmbeddingProvider,
        vectorstore: FAISSVectorStore,
        document_store: DocumentStore,
        reranker: BasicReranker,
        candidate_multiplier: int = 4,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._vectorstore = vectorstore
        self._document_store = document_store
        self._reranker = reranker
        self._candidate_multiplier = max(candidate_multiplier, 1)

    def retrieve(self, request: RAGQueryRequest) -> list[RetrievedChunk]:
        """Retrieve and rerank knowledge chunks."""
        if self._vectorstore.count == 0:
            return []

        top_k = request.top_k or 3
        candidate_count = max(top_k, top_k * self._candidate_multiplier)
        search_matches = self._vectorstore.search(
            self._embedding_provider.embed_query(self._build_search_text(request)),
            candidate_count,
        )
        results: list[RetrievedChunk] = []
        for match in search_matches:
            chunk = self._document_store.get_chunk(match.chunk_id)
            if chunk is None:
                continue
            results.append(
                RetrievedChunk(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    text=chunk.text,
                    source=chunk.source,
                    score=match.score,
                    metadata=chunk.metadata,
                )
            )
        return self._reranker.rerank(
            query=request.query,
            results=results,
            top_k=top_k,
            task_type=request.task_type,
            region=request.region,
            crop_type=request.crop_type,
            context=request.context,
        )

    @staticmethod
    def _build_search_text(request: RAGQueryRequest) -> str:
        parts = [request.query]
        for value in [request.task_type, request.region, request.crop_type]:
            if value:
                parts.append(value)
        if request.context:
            parts.extend([f"{key}: {value}" for key, value in request.context.items()])
        return " ".join(parts)
