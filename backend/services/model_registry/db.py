"""Database setup for the model registry service."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from shared.config.settings import get_settings
from services.model_registry.models import Base

logger = logging.getLogger(__name__)
settings = get_settings()


def normalize_database_url(database_url: str) -> str:
    """Normalize database URLs for SQLAlchemy and psycopg."""
    if database_url.startswith("postgresql://") and "+psycopg" not in database_url:
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    return database_url


def create_engine_for_url(database_url: str | None = None) -> Engine:
    """Create a SQLAlchemy engine for SQLite or PostgreSQL."""
    resolved_url = normalize_database_url(database_url or settings.database_url)
    engine_kwargs: dict[str, object] = {
        "future": True,
        "pool_pre_ping": True,
    }
    if resolved_url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(resolved_url, **engine_kwargs)


def redact_database_url(database_url: str) -> str:
    """Redact credentials before logging a database URL."""
    if "@" not in database_url or "://" not in database_url:
        return database_url
    prefix, suffix = database_url.split("://", 1)
    if "@" not in suffix:
        return database_url
    _, host_part = suffix.rsplit("@", 1)
    return f"{prefix}://***@{host_part}"


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to the provided engine."""
    return sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )


engine = create_engine_for_url(settings.database_url)
SessionLocal = create_session_factory(engine)


def configure_database(database_url: str | None = None) -> tuple[Engine, sessionmaker[Session]]:
    """Reconfigure the global engine and session factory."""
    global engine, SessionLocal
    engine.dispose()
    resolved_url = normalize_database_url(database_url or settings.database_url)
    engine = create_engine_for_url(resolved_url)
    SessionLocal = create_session_factory(engine)
    logger.info(
        "model_registry_database_configured | url=%s",
        redact_database_url(resolved_url),
    )
    return engine, SessionLocal


async def get_db() -> AsyncGenerator[Session, None]:
    """FastAPI dependency yielding a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(target_engine: Engine | None = None) -> None:
    """Create tables for the model registry service."""
    active_engine = target_engine or engine
    Base.metadata.create_all(bind=active_engine)
    logger.info("model_registry_database_initialized")
