"""Tests for the confidence evaluation service."""
import pytest
from unittest.mock import patch

from services.confidence_service.client import LocalConfidenceServiceClient
from services.confidence_service.service import ConfidenceService
from services.confidence_service.schemas import (
    ConfidenceRequest,
    ImageConfidenceInput,
    TextConfidenceInput,
    WorkflowConfidenceInput,
)
from services.confidence_service.fusion import fuse_confidence_results
from services.confidence_service.image_confidence import score_image_confidence
from services.confidence_service.text_confidence import score_text_confidence
from services.confidence_service.workflow_confidence import score_workflow_confidence


def _make_image_input(
    model_confidence: float = 0.9,
    affected_area: float = 1000.0,
    polygon_count: int = 1,
    mask_uri: str | None = None,
    task_type: str | None = None,
) -> ImageConfidenceInput:
    return ImageConfidenceInput(
        model_confidence=model_confidence,
        affected_area=affected_area,
        polygon_count=polygon_count,
        mask_uri=mask_uri,
        task_type=task_type,
    )


def _make_text_input(
    retrieved_source_count: int = 3,
    average_retrieval_score: float = 0.8,
    has_rag_summary: bool = True,
) -> TextConfidenceInput:
    return TextConfidenceInput(
        retrieved_source_count=retrieved_source_count,
        average_retrieval_score=average_retrieval_score,
        has_rag_summary=has_rag_summary,
    )


def _make_workflow_input(
    model_exists: bool = True,
    training_triggered: bool = False,
    error_count: int = 0,
    status: str = "completed",
) -> WorkflowConfidenceInput:
    return WorkflowConfidenceInput(
        model_exists=model_exists,
        training_triggered=training_triggered,
        error_count=error_count,
        status=status,
    )


class TestImageConfidence:
    """Test image confidence scoring logic."""

    def test_high_model_confidence(self):
        payload = _make_image_input(model_confidence=0.95)
        result = score_image_confidence(payload)
        assert result.score >= 0.8
        assert result.label == "high"

    def test_low_model_confidence(self):
        payload = _make_image_input(model_confidence=0.2, affected_area=0)
        result = score_image_confidence(payload)
        assert result.score < 0.5
        assert result.label == "low"

    def test_polygon_count_boost(self):
        no_poly = _make_image_input(model_confidence=0.8, polygon_count=0)
        with_poly = _make_image_input(model_confidence=0.8, polygon_count=5)
        result_no = score_image_confidence(no_poly)
        result_with = score_image_confidence(with_poly)
        assert result_with.score >= result_no.score

    def test_zero_affected_area_penalty(self):
        with_area = _make_image_input(model_confidence=0.9, affected_area=500.0)
        no_area = _make_image_input(model_confidence=0.9, affected_area=0)
        result_with = score_image_confidence(with_area)
        result_without = score_image_confidence(no_area)
        assert result_without.score < result_with.score

    def test_missing_mask_no_penalty_when_no_uri(self):
        payload = _make_image_input(model_confidence=0.9, mask_uri=None)
        result = score_image_confidence(payload)
        # No mask URI means inspect_mask_artifact returns available=False,
        # no penalty applied for missing mask
        assert result.score >= 0.85


class TestTextConfidence:
    """Test text/RAG confidence scoring logic."""

    def test_good_rag_inputs(self):
        payload = _make_text_input(
            retrieved_source_count=4,
            average_retrieval_score=0.9,
            has_rag_summary=True,
        )
        result = score_text_confidence(payload)
        assert result.score >= 0.55

    def test_no_sources(self):
        payload = _make_text_input(
            retrieved_source_count=0,
            average_retrieval_score=0.0,
            has_rag_summary=False,
        )
        result = score_text_confidence(payload)
        assert result.score < 0.5
        assert result.label == "low"

    def test_summary_boost(self):
        no_summary = _make_text_input(has_rag_summary=False)
        with_summary = _make_text_input(has_rag_summary=True)
        result_no = score_text_confidence(no_summary)
        result_with = score_text_confidence(with_summary)
        assert result_with.score > result_no.score


class TestWorkflowConfidence:
    """Test workflow confidence scoring logic."""

    def test_ideal_workflow(self):
        payload = _make_workflow_input(
            model_exists=True,
            training_triggered=False,
            error_count=0,
            status="completed",
        )
        result = score_workflow_confidence(payload)
        assert result.score >= 0.8
        assert result.label == "high"

    def test_training_triggered_penalty(self):
        no_training = _make_workflow_input(training_triggered=False)
        with_training = _make_workflow_input(training_triggered=True)
        result_no = score_workflow_confidence(no_training)
        result_with = score_workflow_confidence(with_training)
        assert result_with.score < result_no.score

    def test_error_count_penalty(self):
        no_errors = _make_workflow_input(error_count=0)
        with_errors = _make_workflow_input(error_count=2)
        result_no = score_workflow_confidence(no_errors)
        result_with = score_workflow_confidence(with_errors)
        assert result_with.score < result_no.score

    def test_non_completed_status_penalty(self):
        completed = _make_workflow_input(status="completed")
        failed = _make_workflow_input(status="failed")
        result_completed = score_workflow_confidence(completed)
        result_failed = score_workflow_confidence(failed)
        assert result_failed.score < result_completed.score


class TestFusion:
    """Test confidence fusion logic."""

    def test_high_confidence_fusion(self):
        from services.confidence_service.schemas import SubConfidenceResult
        image = SubConfidenceResult(score=0.95, label="high", reason="test")
        text = SubConfidenceResult(score=0.90, label="high", reason="test")
        workflow = SubConfidenceResult(score=0.92, label="high", reason="test")
        result = fuse_confidence_results(
            image_result=image,
            text_result=text,
            workflow_result=workflow,
        )
        assert result.final_confidence >= 0.8
        assert result.final_label == "high"

    def test_low_confidence_fusion(self):
        from services.confidence_service.schemas import SubConfidenceResult
        image = SubConfidenceResult(score=0.2, label="low", reason="test")
        text = SubConfidenceResult(score=0.15, label="low", reason="test")
        workflow = SubConfidenceResult(score=0.3, label="low", reason="test")
        result = fuse_confidence_results(
            image_result=image,
            text_result=text,
            workflow_result=workflow,
        )
        assert result.final_confidence < 0.5
        assert result.final_label == "low"


class TestLocalConfidenceServiceClient:
    """Test the local confidence service client used by the orchestrator."""

    def test_evaluate_high_confidence(self):
        client = LocalConfidenceServiceClient()
        result = client.evaluate(
            request_id="test-001",
            inference_result={"confidence": 0.95, "affected_area": 1000.0, "polygons": [{"id": 1}]},
            rag_result={"sources": ["s1", "s2", "s3"], "summary": "摘要", "results": []},
            report_result=None,
            training_triggered=False,
            model_exists=True,
            status="completed",
            error_count=0,
        )
        assert result.final_confidence >= 0.7
        assert result.final_label in ("high", "medium")

    def test_evaluate_low_confidence(self):
        client = LocalConfidenceServiceClient()
        result = client.evaluate(
            request_id="test-002",
            inference_result={"confidence": 0.2, "affected_area": 0.0, "polygons": []},
            rag_result={"sources": [], "summary": "", "results": []},
            report_result=None,
            training_triggered=True,
            model_exists=False,
            status="failed",
            error_count=3,
        )
        assert result.final_confidence < 0.6

    def test_evaluate_with_task_type(self):
        client = LocalConfidenceServiceClient()
        result = client.evaluate(
            request_id="test-003",
            inference_result={"confidence": 0.9, "affected_area": 500.0, "polygons": []},
            rag_result={"sources": ["s1"], "summary": "摘要", "results": []},
            report_result=None,
            training_triggered=False,
            model_exists=True,
            status="completed",
            error_count=0,
            task_type="baldness_detection",
        )
        assert result.final_confidence > 0

    def test_evaluate_no_inference_result(self):
        client = LocalConfidenceServiceClient()
        result = client.evaluate(
            request_id="test-004",
            inference_result=None,
            rag_result=None,
            report_result=None,
            training_triggered=False,
            model_exists=True,
            status="completed",
            error_count=0,
        )
        # Should still produce a result even with no inference
        assert result.final_confidence >= 0
