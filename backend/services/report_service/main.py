"""FastAPI application entrypoint for the report service."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from services.report_service.config import ReportServiceConfig, get_report_service_config
from services.report_service.routers.health import router as health_router
from services.report_service.routers.report import router as report_router
from services.report_service.service import ReportService
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
    config: ReportServiceConfig | None = None,
    service: ReportService | None = None,
) -> FastAPI:
    """Create the FastAPI app for the report service."""
    resolved_config = config or get_report_service_config()
    resolved_service = service or ReportService(config=resolved_config)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        logger.info(
            "report_service_started | output_dir=%s | template_dir=%s",
            resolved_config.report_output_dir,
            resolved_config.report_template_dir,
        )
        try:
            yield
        finally:
            logger.info("report_service_stopped")

    application = FastAPI(
        title=resolved_config.report_service_name,
        version="0.1.0",
        description="Independent HTML report generation service.",
        lifespan=lifespan,
    )
    application.state.report_service = resolved_service
    application.state.report_config = resolved_config

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        logger.warning("report_service_validation_failed | errors=%s", exc.errors())
        return _error_response(422, "validation_error", str(exc))

    application.include_router(health_router)
    application.include_router(report_router)

    @application.get("/", response_model=PingResponse, tags=["system"])
    async def root() -> PingResponse:
        return PingResponse(
            message="pong",
            service=resolved_config.report_service_name,
            environment=settings.app_env,
        )

    return application


app = create_app()
