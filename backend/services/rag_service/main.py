"""FastAPI application entrypoint for the RAG service."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from services.rag_service.config import RAGServiceConfig, get_rag_service_config
from services.rag_service.routers.health import router as health_router
from services.rag_service.routers.ingest import router as ingest_router
from services.rag_service.routers.query import router as query_router
from services.rag_service.service import RAGService, RAGServiceError
from shared.config.settings import get_settings
from shared.logging import configure_logging
from shared.schemas.common import ErrorResponse, PingResponse

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


def _error_response(status_code: int, error_code: str, detail: str) -> JSONResponse:
    payload = ErrorResponse(error_code=error_code, detail=detail)
    return JSONResponse(status_code=status_code, content=payload.model_dump())


def create_app(
    *,
    config: RAGServiceConfig | None = None,
    service: RAGService | None = None,
) -> FastAPI:
    """Create the FastAPI app for the RAG service."""
    resolved_config = config or get_rag_service_config()
    resolved_service = service or RAGService(config=resolved_config)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        logger.info(
            "rag_service_started | vectorstore_dir=%s | use_mock_embedding=%s",
            resolved_config.vectorstore_dir,
            resolved_config.use_mock_embedding,
        )
        try:
            yield
        finally:
            logger.info("rag_service_stopped")

    application = FastAPI(
        title=resolved_config.rag_service_name,
        version="0.1.0",
        description="Independent retrieval-augmented knowledge service.",
        lifespan=lifespan,
    )
    application.state.rag_service = resolved_service
    application.state.rag_config = resolved_config

    @application.exception_handler(RAGServiceError)
    async def handle_rag_service_error(
        _: Request,
        exc: RAGServiceError,
    ) -> JSONResponse:
        logger.warning(
            "rag_service_request_failed | error_code=%s | detail=%s",
            exc.error_code,
            exc.detail,
        )
        return _error_response(exc.status_code, exc.error_code, exc.detail)

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        logger.warning("rag_service_validation_failed | errors=%s", exc.errors())
        return _error_response(422, "validation_error", str(exc))

    application.include_router(health_router)
    application.include_router(ingest_router)
    application.include_router(query_router)

    @application.get("/", response_model=PingResponse, tags=["system"])
    async def root() -> PingResponse:
        return PingResponse(
            message="pong",
            service=resolved_config.rag_service_name,
            environment=settings.app_env,
        )

    return application


app = create_app()
