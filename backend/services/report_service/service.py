"""Business service for HTML report generation."""

from __future__ import annotations

import logging
from pathlib import Path

from services.report_service.builder import ReportBuilder
from services.report_service.config import ReportServiceConfig, get_report_service_config
from services.report_service.schemas import ReportRequest, ReportResponse

logger = logging.getLogger(__name__)


class ReportService:
    """Generate and persist HTML reports from structured inputs."""

    def __init__(
        self,
        *,
        config: ReportServiceConfig | None = None,
        builder: ReportBuilder | None = None,
    ) -> None:
        self._config = config or get_report_service_config()
        self._builder = builder or ReportBuilder(config=self._config)

    def generate_report(self, request: ReportRequest) -> ReportResponse:
        """Generate a report and persist it to the configured output directory."""
        logger.info("report_generation_started | request_id=%s", request.request_id)
        try:
            result = self._builder.build_html_report(request)
            output_dir = Path(self._config.report_output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            report_path = output_dir / f"{request.request_id}.html"
            html_to_write = result.html or ""
            report_path.write_text(html_to_write, encoding="utf-8")
            final_result = result.model_copy(
                update={
                    "report_path": str(report_path),
                    "html": html_to_write if self._config.embed_html_in_response else None,
                }
            )
        except Exception as exc:
            logger.exception("report_generation_failed | request_id=%s", request.request_id)
            return ReportResponse(
                request_id=request.request_id,
                success=False,
                result=None,
                message=f"report generation failed: {exc}",
            )

        logger.info(
            "report_generation_succeeded | request_id=%s | report_path=%s",
            request.request_id,
            final_result.report_path,
        )
        return ReportResponse(
            request_id=request.request_id,
            success=True,
            result=final_result,
            message="report generated",
        )

    def get_health_snapshot(self) -> dict[str, str]:
        """Return a health snapshot for the report service."""
        return {
            "template_dir": self._config.report_template_dir,
            "output_dir": self._config.report_output_dir,
        }
