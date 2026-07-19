"""HTML report builder using Jinja2 templates."""

from __future__ import annotations

from datetime import datetime, timezone

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

from services.report_service.charts import build_chart_context
from services.report_service.config import ReportServiceConfig, get_report_service_config
from services.report_service.schemas import ReportRequest, ReportResult


class ReportBuilder:
    """Build HTML reports from structured workflow results."""

    def __init__(self, config: ReportServiceConfig | None = None) -> None:
        self._config = config or get_report_service_config()
        self._environment = Environment(
            loader=FileSystemLoader(self._config.report_template_dir),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def build_html_report(self, request: ReportRequest) -> ReportResult:
        """Render a report HTML document from structured inputs."""
        try:
            template = self._environment.get_template("report.html.j2")
        except TemplateNotFound as exc:
            raise FileNotFoundError(
                f"report template not found in {self._config.report_template_dir}"
            ) from exc

        chart_context = build_chart_context(request)
        sections = ["summary"]
        if request.inference is not None:
            sections.append("inference")
        if request.rag is not None:
            sections.append("rag")
        if request.confidence is not None:
            sections.append("confidence")

        generated_at = datetime.now(timezone.utc)
        report_id = f"report-{request.request_id}"
        html = template.render(
            request=request,
            generated_at=generated_at.isoformat(),
            chart_context=chart_context,
            extra=chart_context,
            report_id=report_id,
        )
        return ReportResult(
            report_id=report_id,
            report_title=request.title,
            html=html,
            report_path="",
            generated_at=generated_at,
            sections=sections,
            chart_context=chart_context,
        )
