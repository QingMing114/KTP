"""Business service for workflow dashboard generation."""

from __future__ import annotations

import logging

from services.visualization_service.builder import VisualizationBuilder
from services.visualization_service.config import (
    VisualizationServiceConfig,
    get_visualization_service_config,
)
from services.visualization_service.schemas import VisualizationRequest, VisualizationResponse

logger = logging.getLogger(__name__)


class VisualizationService:
    """Generate and persist workflow visualization dashboards."""

    def __init__(
        self,
        *,
        config: VisualizationServiceConfig | None = None,
        builder: VisualizationBuilder | None = None,
    ) -> None:
        self._config = config or get_visualization_service_config()
        self._builder = builder or VisualizationBuilder(config=self._config)

    def generate_visualization(self, request: VisualizationRequest) -> VisualizationResponse:
        """Build a dashboard and return a structured service response."""
        logger.info("visualization_generation_started | request_id=%s", request.request_id)
        try:
            result = self._builder.build_dashboard(request)
        except Exception as exc:
            logger.exception(
                "visualization_generation_failed | request_id=%s",
                request.request_id,
            )
            return VisualizationResponse(
                request_id=request.request_id,
                success=False,
                result=None,
                message=f"visualization generation failed: {exc}",
            )

        logger.info(
            "visualization_generation_succeeded | request_id=%s | dashboard=%s",
            request.request_id,
            result.dashboard_path,
        )
        return VisualizationResponse(
            request_id=request.request_id,
            success=True,
            result=result,
            message="visualization generated",
        )

    def get_health_snapshot(self) -> dict[str, str]:
        """Return a simple health snapshot for the visualization service."""
        return {
            "template_dir": self._config.visualization_template_dir,
            "output_dir": self._config.visualization_output_dir,
        }
