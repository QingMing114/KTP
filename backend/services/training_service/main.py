"""FastAPI wrapper around the Temporal training service."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from services.training_service.client import (
    TrainingServiceClientError,
    start_training_workflow,
)
from services.training_service.config import get_training_service_config
from services.training_service.schemas import (
    TrainingRequest,
    TrainingWorkflowStartResponse,
)
from shared.config.settings import get_settings
from shared.logging import configure_logging
from shared.schemas.common import ErrorResponse, HealthResponse

settings = get_settings()
config = get_training_service_config()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


def _error_response(status_code: int, error_code: str, detail: str) -> JSONResponse:
    payload = ErrorResponse(error_code=error_code, detail=detail)
    return JSONResponse(status_code=status_code, content=payload.model_dump())


def create_app() -> FastAPI:
    """Create the FastAPI app for the training service."""

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        logger.info(
            "training_service_started | temporal_server=%s | task_queue=%s",
            config.temporal_server_url,
            config.temporal_task_queue,
        )
        try:
            yield
        finally:
            logger.info("training_service_stopped")

    application = FastAPI(
        title=config.training_service_name,
        version="0.1.0",
        description="Temporal-based training service for long-running model training flows.",
        lifespan=lifespan,
    )

    @application.exception_handler(TrainingServiceClientError)
    async def handle_training_client_error(
        _: Request,
        exc: TrainingServiceClientError,
    ) -> JSONResponse:
        logger.warning("training_service_request_failed | detail=%s", str(exc))
        return _error_response(503, "training_service_unavailable", str(exc))

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        logger.warning("training_service_validation_failed | errors=%s", exc.errors())
        return _error_response(422, "validation_error", str(exc))

    @application.get("/health", response_model=HealthResponse, tags=["health"])
    async def health_check() -> HealthResponse:
        return HealthResponse(
            service=config.training_service_name,
            status="ok",
            environment=settings.app_env,
            checks={
                "temporal": "configured",
                "model_registry": "configured",
            },
        )

    @application.post(
        "/training/start",
        response_model=TrainingWorkflowStartResponse,
        tags=["training"],
    )
    async def start_training(
        request: TrainingRequest,
    ) -> TrainingWorkflowStartResponse:
        return await start_training_workflow(request)

    return application


app = create_app()
