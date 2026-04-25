"""Orchestrator client for workflow visualization generation."""

from __future__ import annotations

from services.visualization_service.client import LocalVisualizationServiceClient
from services.visualization_service.config import VisualizationServiceConfig


class VisualizationServiceClient:
    """Thin orchestrator wrapper around the local visualization client."""

    def __init__(self, *, config: VisualizationServiceConfig) -> None:
        self._client = LocalVisualizationServiceClient(config=config)

    def build_visualization(self, **kwargs):
        return self._client.build_visualization(**kwargs)
