"""SQLAlchemy ORM models for the model registry service."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum as SAEnum, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from services.model_registry.schemas import ModelStatus


class Base(DeclarativeBase):
    """Declarative base for the model registry service."""


class RegisteredModel(Base):
    """Persisted metadata for a trained model artifact."""

    __tablename__ = "registered_models"
    __table_args__ = (
        UniqueConstraint(
            "region",
            "crop_type",
            "task_type",
            "model_name",
            "model_version",
            name="uq_registered_models_identity",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    region: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    crop_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_uri: Mapped[str] = mapped_column(Text, nullable=False)
    metrics_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[ModelStatus] = mapped_column(
        SAEnum(ModelStatus, native_enum=False),
        nullable=False,
        default=ModelStatus.TRAINING,
        index=True,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
