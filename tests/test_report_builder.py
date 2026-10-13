"""Unit tests for the HTML report builder."""

from __future__ import annotations

from pathlib import Path
import re

from services.report_service.builder import ReportBuilder
from services.report_service.config import ReportServiceConfig
from services.report_service.schemas import (
    ReportInputConfidence,
    ReportInputInference,
    ReportInputRAG,
    ReportInputSummary,
    ReportRequest,
)

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "backend" / "services" / "report_service" / "templates"


def test_report_builder_renders_expected_sections(tmp_path: Path) -> None:
    config = ReportServiceConfig(
        REPORT_SERVICE_NAME="report-service",
        REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
        REPORT_TEMPLATE_DIR=str(TEMPLATE_DIR),
        EMBED_HTML_IN_RESPONSE=True,
        GENERATE_CHARTS=True,
    )
    builder = ReportBuilder(config=config)

    result = builder.build_html_report(
        ReportRequest(
            request_id="req-report-builder-001",
            title="河南小麦长势报告",
            user_query="评估河南小麦长势。",
            region="henan",
            crop_type="wheat",
            task_type="crop_health_detection",
            summary=ReportInputSummary(
                overview="该报告由工作流输出自动生成。",
                key_findings=["推理置信度较高。"],
            ),
            inference=ReportInputInference(
                model_name="wheat-health-segmentation",
                model_version="v1",
                affected_area=1280.5,
                confidence=0.91,
                mask_uri="/tmp/mask.png",
                polygons=[{"id": "poly-1"}],
                positive_ratio=0.37,
                warnings=["mask coverage is near-total and should be reviewed manually"],
            ),
            rag=ReportInputRAG(
                summary="已检索河南小麦相关农学背景。",
                sources=["local://knowledge/henan-wheat"],
                results=[],
            ),
            confidence=ReportInputConfidence(
                image_confidence=0.41,
                text_confidence=0.82,
                workflow_confidence=0.88,
                final_confidence=0.62,
                final_label="medium",
                explanation="掩膜结构异常，导致图像置信度下降。",
                warnings=["mask contains a single positive value across the full image"],
            ),
            extra_metadata={},
        )
    )

    rendered = result.html or ""
    assert result.sections == ["summary", "inference", "rag", "confidence"]
    for value in [
        "河南小麦长势报告", "该报告由工作流输出自动生成。", "推理置信度较高。",
        "wheat-health-segmentation", "已检索河南小麦相关农学背景。",
        "local://knowledge/henan-wheat", "掩膜结构异常，导致图像置信度下降。",
        "mask coverage is near-total and should be reviewed manually",
        "mask contains a single positive value across the full image",
    ]:
        assert value in rendered
    # The health dashboard displays the healthy share, complementary to affected pixels.
    ratio = re.search(r'id="lbl-kpi-2-val">\s*([\d.]+)', rendered)
    assert ratio and float(ratio.group(1)) == 63.0
