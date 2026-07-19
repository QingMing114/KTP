"""Tests for the report service: charts.py and builder.py"""
import pytest
from services.report_service.charts import build_chart_context
from services.report_service.schemas import (
    ReportRequest, ReportInputSummary, ReportInputInference,
    ReportInputRAG, ReportInputConfidence,
)
from services.report_service.builder import ReportBuilder


def _make_request(**overrides) -> ReportRequest:
    defaults = dict(
        request_id="test-001",
        title="测试报告",
        user_query="帮我分析影像",
        region="henan",
        crop_type="wheat",
        task_type="baldness_detection",
        summary=ReportInputSummary(overview="概述", key_findings=["发现1"]),
        inference=ReportInputInference(
            model_name="TestModel",
            model_version="v1",
            affected_area=1000.0,
            confidence=0.85,
            mask_uri="/tmp/mask.tif",
            polygons=[{"id": "p1", "points": [(0, 0), (1, 1)]}],
            positive_ratio=0.1,
        ),
        rag=ReportInputRAG(summary="知识摘要", sources=["src1"]),
        confidence=ReportInputConfidence(
            image_confidence=0.9,
            text_confidence=0.8,
            workflow_confidence=0.85,
            final_confidence=0.85,
            final_label="high",
            explanation="测试解释",
        ),
    )
    defaults.update(overrides)
    return ReportRequest(**defaults)


class TestBuildChartContext:
    def test_basic_fields(self):
        req = _make_request()
        ctx = build_chart_context(req)
        assert "class_distribution_chart" in ctx
        assert "confidence_gauge" in ctx
        assert "area_breakdown" in ctx

    def test_sensors_defaults(self):
        req = _make_request()
        ctx = build_chart_context(req)
        assert "sensors" in ctx
        assert "opt" in ctx["sensors"]
        assert "sar" in ctx["sensors"]

    def test_sensors_from_extra(self):
        req = _make_request(extra_metadata={
            "sensors": {"opt": "GF-2", "sar": "TerraSAR-X", "gdd": "+30 ℃·d", "sm": "20 %"},
        })
        ctx = build_chart_context(req)
        assert ctx["sensors"]["opt"] == "GF-2"
        assert ctx["sensors"]["sar"] == "TerraSAR-X"

    def test_prescriptions_defaults(self):
        req = _make_request()
        ctx = build_chart_context(req)
        assert "prescriptions" in ctx
        assert "p1" in ctx["prescriptions"]

    def test_prescriptions_from_extra(self):
        req = _make_request(extra_metadata={
            "prescriptions": {"p1": "处方1", "p2": "处方2", "p3": "处方3"},
        })
        ctx = build_chart_context(req)
        assert ctx["prescriptions"]["p1"] == "处方1"

    def test_gis_coords_henan(self):
        req = _make_request(region="henan")
        ctx = build_chart_context(req)
        assert "34.0294" in ctx["gis_coords"]

    def test_gis_coords_shandong(self):
        req = _make_request(region="shandong")
        ctx = build_chart_context(req)
        assert "36.7868" in ctx["gis_coords"]

    def test_gis_coords_unknown_defaults_henan(self):
        req = _make_request(region="unknown_region")
        ctx = build_chart_context(req)
        assert "34.0294" in ctx["gis_coords"]

    def test_pixel_to_mu_ratio_default(self):
        req = _make_request()
        ctx = build_chart_context(req)
        assert ctx["pixel_to_mu_ratio"] == 0.1

    def test_pixel_to_mu_ratio_from_extra(self):
        req = _make_request(extra_metadata={"pixel_to_mu_ratio": 0.05})
        ctx = build_chart_context(req)
        assert ctx["pixel_to_mu_ratio"] == 0.05

    def test_positive_negative_analysis(self):
        req = _make_request(extra_metadata={
            "positive_analysis": "积极分析",
            "negative_analysis": "消极分析",
        })
        ctx = build_chart_context(req)
        assert ctx["positive_analysis"] == "积极分析"
        assert ctx["negative_analysis"] == "消极分析"

    def test_est_loss(self):
        req = _make_request(extra_metadata={"est_loss": "5.2 %"})
        ctx = build_chart_context(req)
        assert ctx["est_loss"] == "5.2 %"

    def test_confidence_gauge_high(self):
        req = _make_request()
        ctx = build_chart_context(req)
        assert ctx["confidence_gauge"]["available"] is True
        assert ctx["confidence_gauge"]["level"] == "high"

    def test_area_breakdown(self):
        req = _make_request()
        ctx = build_chart_context(req)
        assert ctx["area_breakdown"]["available"] is True
        assert ctx["area_breakdown"]["polygon_count"] == 1

    def test_no_inference(self):
        req = _make_request(inference=None, confidence=None)
        ctx = build_chart_context(req)
        assert ctx["confidence_gauge"]["available"] is False
        assert ctx["area_breakdown"]["available"] is False


class TestReportBuilder:
    def test_build_html_report(self):
        req = _make_request()
        builder = ReportBuilder()
        result = builder.build_html_report(req)
        assert result.report_id == "report-test-001"
        assert len(result.html) > 100
        assert "测试报告" in result.html

    def test_build_html_report_minimal(self):
        req = _make_request(
            inference=None, rag=None, confidence=None,
            summary=ReportInputSummary(overview="", key_findings=[]),
        )
        builder = ReportBuilder()
        result = builder.build_html_report(req)
        assert len(result.html) > 100
