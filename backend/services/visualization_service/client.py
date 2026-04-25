"""Local orchestrator client for the visualization service."""

from __future__ import annotations

import logging

from services.visualization_service.config import (
    VisualizationServiceConfig,
    get_visualization_service_config,
)
from services.visualization_service.schemas import VisualizationRequest
from services.visualization_service.service import VisualizationService
from shared.schemas.service_results import VisualizationServiceResult

logger = logging.getLogger(__name__)


class VisualizationServiceClientError(Exception):
    """Raised when local visualization generation cannot be completed."""


class LocalVisualizationServiceClient:
    """Run the local visualization service from orchestrator synchronous code."""

    def __init__(
        self,
        *,
        config: VisualizationServiceConfig | None = None,
        service: VisualizationService | None = None,
    ) -> None:
        self._config = config or get_visualization_service_config()
        self._service = service or VisualizationService(config=self._config)

    def build_visualization(self, **kwargs) -> VisualizationServiceResult:
        """Generate a workflow dashboard and normalize the output for orchestrator use."""
        request = VisualizationRequest(**kwargs)
        logger.info("local_visualization_execution_started | request_id=%s", request.request_id)
        response = self._service.generate_visualization(request)
        if not response.success or response.result is None:
            raise VisualizationServiceClientError(response.message)

        logger.info(
            "local_visualization_execution_succeeded | request_id=%s | dashboard=%s",
            request.request_id,
            response.result.dashboard_path,
        )
        return VisualizationServiceResult(
            visualization_uri=response.result.dashboard_path,
            title=response.result.title,
            sections=response.result.sections,
            visualization_id=response.result.visualization_id,
            artifact_dir=response.result.artifact_dir,
            snapshot_path=response.result.snapshot_path,
            html=response.result.html,
            generated_at=response.result.generated_at.isoformat(),
            artifacts=[artifact.model_dump() for artifact in response.result.artifacts],
        )
