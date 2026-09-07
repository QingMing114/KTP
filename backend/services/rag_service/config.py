"""Configuration for the RAG retrieval service."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.config.paths import RUNTIME_DIR


class RAGServiceConfig(BaseSettings):
    """Settings used by the RAG service runtime."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    rag_service_name: str = Field(
        default="rag-service",
        validation_alias="RAG_SERVICE_NAME",
    )
    vectorstore_dir: str = Field(
        default=str(RUNTIME_DIR / "rag_store"),
        validation_alias="VECTORSTORE_DIR",
    )
    default_top_k: int = Field(
        default=3,
        validation_alias="DEFAULT_TOP_K",
    )
    use_mock_embedding: bool = Field(
        default=True,
        validation_alias="USE_MOCK_EMBEDDING",
    )
    embedding_model_name: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        validation_alias="EMBEDDING_MODEL_NAME",
    )
    embedding_dimension: int = Field(
        default=128,
        validation_alias="RAG_EMBEDDING_DIMENSION",
    )
    chunk_size: int = Field(
        default=120,
        validation_alias="RAG_CHUNK_SIZE",
    )
    chunk_overlap: int = Field(
        default=20,
        validation_alias="RAG_CHUNK_OVERLAP",
    )
    search_candidate_multiplier: int = Field(
        default=4,
        validation_alias="RAG_SEARCH_CANDIDATE_MULTIPLIER",
    )


@lru_cache(maxsize=1)
def get_rag_service_config() -> RAGServiceConfig:
    """Return the cached RAG service configuration."""
    return RAGServiceConfig()
