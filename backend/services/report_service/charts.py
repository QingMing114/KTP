"""Chart context helpers for the report service."""

from __future__ import annotations

from services.report_service.schemas import ReportRequest


def build_chart_context(request: ReportRequest) -> dict[str, object]:
    """Return lightweight chart-ready data for future front-end rendering."""
    inference = request.inference
    confidence = request.confidence
    return {
        "affected_area_series": [
            {
                "label": request.crop_type or "target",
                "value": round(inference.affected_area, 4) if inference else 0.0,
            }
        ],
        "confidence_series": [
            {
                "label": "image",
                "value": round(confidence.image_confidence, 4) if confidence else 0.0,
            },
            {
                "label": "text",
                "value": round(confidence.text_confidence, 4) if confidence else 0.0,
            },
            {
                "label": "workflow",
                "value": round(confidence.workflow_confidence, 4) if confidence else 0.0,
            },
            {
                "label": "final",
                "value": round(confidence.final_confidence, 4) if confidence else 0.0,
            },
        ],
    }
