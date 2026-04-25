"""Orchestrator client for report generation."""

from __future__ import annotations

from services.report_service.client import LocalReportServiceClient
from services.report_service.config import ReportServiceConfig


class ReportServiceClient:
    """Thin orchestrator wrapper around the local report client."""

    def __init__(self, *, config: ReportServiceConfig) -> None:
        self._client = LocalReportServiceClient(config=config)

    def build_report(self, **kwargs):
        return self._client.build_report(**kwargs)
