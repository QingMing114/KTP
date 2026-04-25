"""Orchestrator client for confidence evaluation."""

from __future__ import annotations

from services.confidence_service.client import LocalConfidenceServiceClient
from services.confidence_service.config import ConfidenceServiceConfig


class ConfidenceServiceClient:
    """Thin orchestrator wrapper around the local confidence client."""

    def __init__(self, *, config: ConfidenceServiceConfig) -> None:
        self._client = LocalConfidenceServiceClient(config=config)

    def evaluate(self, **kwargs):
        return self._client.evaluate(**kwargs)
