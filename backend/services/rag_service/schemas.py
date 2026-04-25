"""Pydantic schemas for RAG ingestion and retrieval."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from shared.schemas.common import BaseSchema


class DocumentIngestRequest(BaseSchema):
    """Request payload for ingesting a knowledge document."""

    document_id: str = Field(..., description="Stable document identifier.")
    title: str = Field(..., description="Human-readable document title.")
    source: str = Field(..., description="Source identifier or URI.")
    text: str = Field(..., description="Full document text to ingest.")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured metadata such as region, crop_type, and task_type.",
    )


class DocumentChunk(BaseSchema):
    """Chunked unit stored in the local vector index."""

    chunk_id: str = Field(..., description="Stable chunk identifier.")
    document_id: str = Field(..., description="Parent document identifier.")
    text: str = Field(..., description="Chunk text.")
    source: str = Field(..., description="Source identifier inherited from the document.")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Chunk metadata preserved from the source document.",
    )


class DocumentIngestResponse(BaseSchema):
    """Response payload for document ingestion."""

    document_id: str = Field(..., description="Document identifier.")
    chunk_count: int = Field(..., description="Number of chunks added to the index.")
    success: bool = Field(..., description="Whether ingestion succeeded.")
    message: str = Field(..., description="Human-readable ingestion outcome.")


class RAGQueryRequest(BaseSchema):
    """Request payload for querying the RAG service."""

    request_id: str = Field(..., description="Stable request identifier.")
    query: str = Field(..., description="Natural-language retrieval query.")
    top_k: int | None = Field(
        default=None,
        description="Desired number of retrieved chunks. Falls back to config default.",
    )
    task_type: str | None = Field(default=None, description="Optional task type context.")
    region: str | None = Field(default=None, description="Optional region context.")
    crop_type: str | None = Field(default=None, description="Optional crop type context.")
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context, including inference summaries or planner hints.",
    )


class RetrievedChunk(BaseSchema):
    """Retrieved chunk returned to orchestrator and other services."""

    chunk_id: str = Field(..., description="Chunk identifier.")
    document_id: str = Field(..., description="Parent document identifier.")
    text: str = Field(..., description="Retrieved text snippet.")
    source: str = Field(..., description="Traceable source URI or identifier.")
    score: float = Field(..., description="Retrieval score after reranking.")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Chunk metadata returned for downstream consumers.",
    )


class RAGQueryResponse(BaseSchema):
    """Structured response returned by the RAG service query API."""

    request_id: str = Field(..., description="Original request identifier.")
    success: bool = Field(..., description="Whether the query succeeded.")
    query: str = Field(..., description="Original query string.")
    results: list[RetrievedChunk] = Field(
        default_factory=list,
        description="Retrieved top-k knowledge chunks.",
    )
    message: str = Field(..., description="Human-readable query outcome.")
