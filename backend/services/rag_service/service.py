"""Business service for document ingestion and RAG retrieval."""

from __future__ import annotations

import logging

from services.rag_service.chunking.text_chunker import TextChunker
from services.rag_service.config import RAGServiceConfig, get_rag_service_config
from services.rag_service.embeddings.base import BaseEmbeddingProvider
from services.rag_service.embeddings.mock_embedding import MockEmbeddingProvider
from services.rag_service.embeddings.sentence_transformer_embedding import (
    SentenceTransformerEmbeddingProvider,
)
from services.rag_service.ingest import DocumentIngester
from services.rag_service.reranker import BasicReranker
from services.rag_service.retriever import Retriever
from services.rag_service.schemas import (
    DocumentIngestRequest,
    DocumentIngestResponse,
    RAGQueryRequest,
    RAGQueryResponse,
)
from services.rag_service.storage.document_store import DocumentStore
from services.rag_service.vectorstore import FAISSVectorStore

logger = logging.getLogger(__name__)


class RAGServiceError(Exception):
    """Base error raised by the RAG service layer."""

    error_code = "rag_service_error"
    status_code = 400

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class RAGValidationError(RAGServiceError):
    """Raised when the RAG service receives invalid inputs."""

    error_code = "rag_validation_error"
    status_code = 400


class RAGService:
    """Orchestrate ingestion, indexing, and retrieval for the RAG service."""

    def __init__(
        self,
        *,
        config: RAGServiceConfig | None = None,
        embedding_provider: BaseEmbeddingProvider | None = None,
        vectorstore: FAISSVectorStore | None = None,
        document_store: DocumentStore | None = None,
        chunker: TextChunker | None = None,
        reranker: BasicReranker | None = None,
    ) -> None:
        self._config = config or get_rag_service_config()
        self._embedding_provider = embedding_provider or self._create_embedding_provider()
        self._vectorstore = vectorstore or FAISSVectorStore(self._config.vectorstore_dir)
        self._document_store = document_store or DocumentStore(self._config.vectorstore_dir)
        self._chunker = chunker or TextChunker(
            chunk_size=self._config.chunk_size,
            chunk_overlap=self._config.chunk_overlap,
        )
        self._reranker = reranker or BasicReranker()
        self._ingester = DocumentIngester(
            chunker=self._chunker,
            embedding_provider=self._embedding_provider,
            vectorstore=self._vectorstore,
            document_store=self._document_store,
        )
        self._retriever = Retriever(
            embedding_provider=self._embedding_provider,
            vectorstore=self._vectorstore,
            document_store=self._document_store,
            reranker=self._reranker,
            candidate_multiplier=self._config.search_candidate_multiplier,
        )

    def ingest_document(self, request: DocumentIngestRequest) -> DocumentIngestResponse:
        """Ingest a document into the local RAG knowledge base."""
        logger.info("rag_document_ingest_started | document_id=%s", request.document_id)
        try:
            response = self._ingester.ingest(request)
        except ValueError as exc:
            logger.warning(
                "rag_document_ingest_failed | document_id=%s | detail=%s",
                request.document_id,
                str(exc),
            )
            raise RAGValidationError(str(exc)) from exc
        logger.info(
            "rag_document_ingest_succeeded | document_id=%s | chunk_count=%s",
            request.document_id,
            response.chunk_count,
        )
        return response

    def query(self, request: RAGQueryRequest) -> RAGQueryResponse:
        """Run retrieval for a structured RAG query."""
        top_k = request.top_k or self._config.default_top_k
        resolved_request = request.model_copy(update={"top_k": top_k})
        logger.info(
            "rag_query_started | request_id=%s | top_k=%s | task_type=%s | region=%s | crop_type=%s",
            request.request_id,
            top_k,
            request.task_type,
            request.region,
            request.crop_type,
        )
        results = self._retriever.retrieve(resolved_request)
        logger.info(
            "rag_query_succeeded | request_id=%s | result_count=%s",
            request.request_id,
            len(results),
        )
        message = "rag query completed"
        if not results:
            message = "rag query completed with no matching knowledge chunks"
        return RAGQueryResponse(
            request_id=request.request_id,
            success=True,
            query=request.query,
            results=results,
            message=message,
        )

    def get_health_snapshot(self) -> dict[str, str]:
        """Return health details for service and dependency visibility."""
        return {
            "vectorstore": "ready" if self._vectorstore.count > 0 else "empty",
            "documents": str(self._document_store.document_count),
            "chunks": str(self._document_store.chunk_count),
            "embedding_provider": self._embedding_provider.__class__.__name__,
        }

    def _create_embedding_provider(self) -> BaseEmbeddingProvider:
        if self._config.use_mock_embedding:
            return MockEmbeddingProvider(dimension=self._config.embedding_dimension)
        return SentenceTransformerEmbeddingProvider(
            model_name=self._config.embedding_model_name,
            dimension=self._config.embedding_dimension,
        )
