"""FastAPI application entrypoint for the inference service."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from services.inference_service.config import (
    InferenceServiceConfig,
    get_inference_service_config,
)
from services.inference_service.routers.health import router as health_router
from services.inference_service.routers.inference import router as inference_router
from services.inference_service.service import InferenceService
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
    config: InferenceServiceConfig | None = None,
    service: InferenceService | None = None,
) -> FastAPI:
    """Create the FastAPI app for the inference service."""
    resolved_config = config or get_inference_service_config()
    resolved_service = service or InferenceService(config=resolved_config)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        logger.info(
            "inference_service_started | model_registry=%s | mask_output_dir=%s",
            resolved_config.model_registry_url,
            resolved_config.mask_output_dir,
        )
        try:
            yield
        finally:
            logger.info("inference_service_stopped")

    application = FastAPI(
        title=resolved_config.inference_service_name,
        version="0.1.0",
        description="Dedicated inference service for remote sensing baldness detection tasks.",
        lifespan=lifespan,
    )
    application.state.inference_config = resolved_config
    application.state.inference_service = resolved_service

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        logger.warning("inference_service_validation_failed | errors=%s", exc.errors())
        return _error_response(422, "validation_error", str(exc))

    @application.exception_handler(Exception)
    async def handle_unexpected_error(
        _: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.exception("inference_service_unhandled_error")
        return _error_response(500, "inference_service_error", str(exc))

    application.include_router(health_router)
    application.include_router(inference_router)

    @application.get("/", response_model=PingResponse, tags=["system"])
    async def root() -> PingResponse:
        return PingResponse(
            message="pong",
            service=resolved_config.inference_service_name,
            environment=settings.app_env,
        )

    return application


app = create_app()
