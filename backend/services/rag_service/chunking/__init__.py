"""Chunking utilities for the RAG service."""

from services.rag_service.chunking.text_chunker import TextChunker, chunk_text

__all__ = ["TextChunker", "chunk_text"]
