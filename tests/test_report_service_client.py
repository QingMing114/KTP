"""Tests for report client enrichment of inference sanity warnings."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from services.report_service.client import LocalReportServiceClient
from services.report_service.config import ReportServiceConfig

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "backend" / "services" / "report_service" / "templates"


def test_report_client_surfaces_inference_sanity_warning(tmp_path: Path) -> None:
    mask_path = tmp_path / "full_positive_mask.png"
    Image.fromarray(np.full((12, 12), 255, dtype=np.uint8)).save(mask_path)

    client = LocalReportServiceClient(
        config=ReportServiceConfig(
            REPORT_SERVICE_NAME="report-service",
            REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
            REPORT_TEMPLATE_DIR=str(TEMPLATE_DIR),
            EMBED_HTML_IN_RESPONSE=True,
            GENERATE_CHARTS=True,
        )
    )

    result = client.build_report(
        request_id="req-report-client-001",
        task_type="baldness_detection",
        region="scalp",
        crop_type="hair",
        user_query="分析斑秃严重程度并生成报告。",
        inference_result={
            "model_name": "baldness-rf",
            "model_version": "rf-real-001",
            "affected_area": 144.0,
            "confidence": 0.92,
            "mask_uri": str(mask_path),
            "polygons": [{"id": "poly-1"}],
        },
        rag_result=None,
        confidence_result=None,
        training_triggered=False,
    )

    assert result.html is not None
    assert "推理结果告警" in result.html
    assert "掩膜覆盖率接近全图" in result.html
