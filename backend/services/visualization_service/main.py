"""FastAPI application entrypoint for the visualization service."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from services.visualization_service.config import (
    VisualizationServiceConfig,
    get_visualization_service_config,
)
from services.visualization_service.routers.health import router as health_router
from services.visualization_service.service import VisualizationService
from shared.config.settings import get_settings
from shared.logging import configure_logging
from shared.schemas.common import PingResponse

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


def create_app(
    *,
    config: VisualizationServiceConfig | None = None,
    service: VisualizationService | None = None,
) -> FastAPI:
    """Create the FastAPI app for the visualization service."""
    resolved_config = config or get_visualization_service_config()
    resolved_service = service or VisualizationService(config=resolved_config)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        logger.info(
            "visualization_service_started | output_dir=%s",
            resolved_config.visualization_output_dir,
        )
        try:
            yield
        finally:
            logger.info("visualization_service_stopped")

    application = FastAPI(
        title=resolved_config.visualization_service_name,
        version="0.1.0",
        description="Workflow visualization dashboard service.",
        lifespan=lifespan,
    )
    application.state.visualization_service = resolved_service
    application.state.visualization_config = resolved_config
    application.include_router(health_router)

    @application.get("/", response_model=PingResponse, tags=["system"])
    async def root() -> PingResponse:
        return PingResponse(
            message="pong",
            service=resolved_config.visualization_service_name,
            environment=settings.app_env,
        )

    return application


app = create_app()
