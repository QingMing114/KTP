"""FastAPI application entrypoint for the confidence service."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from services.confidence_service.config import (
    ConfidenceServiceConfig,
    get_confidence_service_config,
)
from services.confidence_service.routers.confidence import router as confidence_router
from services.confidence_service.routers.health import router as health_router
from services.confidence_service.service import ConfidenceService
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
    config: ConfidenceServiceConfig | None = None,
    service: ConfidenceService | None = None,
) -> FastAPI:
    """Create the FastAPI app for the confidence service."""
    resolved_config = config or get_confidence_service_config()
    resolved_service = service or ConfidenceService(config=resolved_config)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        logger.info(
            "confidence_service_started | image_weight=%s | text_weight=%s | workflow_weight=%s",
            resolved_config.image_confidence_weight,
            resolved_config.text_confidence_weight,
            resolved_config.workflow_confidence_weight,
        )
        try:
            yield
        finally:
            logger.info("confidence_service_stopped")

    application = FastAPI(
        title=resolved_config.confidence_service_name,
        version="0.1.0",
        description="Independent confidence evaluation and fusion service.",
        lifespan=lifespan,
    )
    application.state.confidence_service = resolved_service
    application.state.confidence_config = resolved_config

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        logger.warning("confidence_service_validation_failed | errors=%s", exc.errors())
        return _error_response(422, "validation_error", str(exc))

    application.include_router(health_router)
    application.include_router(confidence_router)

    @application.get("/", response_model=PingResponse, tags=["system"])
    async def root() -> PingResponse:
        return PingResponse(
            message="pong",
            service=resolved_config.confidence_service_name,
            environment=settings.app_env,
        )

    return application


app = create_app()
