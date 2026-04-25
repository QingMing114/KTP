"""FastAPI app for the model registry service."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from services.model_registry.db import configure_database, init_db, redact_database_url
from services.model_registry.routers.health import router as health_router
from services.model_registry.routers.models import router as model_router
from services.model_registry.service import ModelRegistryError
from shared.config.settings import get_settings
from shared.logging import configure_logging
from shared.schemas.common import ErrorResponse

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


def _error_response(status_code: int, error_code: str, detail: str) -> JSONResponse:
    payload = ErrorResponse(error_code=error_code, detail=detail)
    return JSONResponse(status_code=status_code, content=payload.model_dump())


def create_app(database_url: str | None = None) -> FastAPI:
    """Create the FastAPI app for the model registry service."""
    engine, _ = configure_database(database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        init_db(engine)
        logger.info(
            "model_registry_service_started | database_url=%s",
            redact_database_url(database_url or settings.database_url),
        )
        try:
            yield
        finally:
            engine.dispose()
            logger.info("model_registry_service_stopped")

    application = FastAPI(
        title="model-registry",
        version="0.1.0",
        description="Model registration and lookup service for the remote sensing system.",
        lifespan=lifespan,
    )

    @application.exception_handler(ModelRegistryError)
    async def handle_model_registry_error(
        _: Request,
        exc: ModelRegistryError,
    ) -> JSONResponse:
        logger.warning(
            "model_registry_request_failed | error_code=%s | detail=%s",
            exc.error_code,
            exc.detail,
        )
        return _error_response(exc.status_code, exc.error_code, exc.detail)

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        logger.warning("model_registry_validation_failed | errors=%s", exc.errors())
        return _error_response(422, "validation_error", str(exc))

    application.include_router(health_router)
    application.include_router(model_router)
    return application


app = create_app()
