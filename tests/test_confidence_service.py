"""Unit tests for the confidence service heuristics and fusion."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from services.confidence_service.schemas import (
    ConfidenceRequest,
    ImageConfidenceInput,
    TextConfidenceInput,
    WorkflowConfidenceInput,
)
from services.confidence_service.service import ConfidenceService


def test_confidence_service_evaluates_and_fuses_subscores() -> None:
    service = ConfidenceService()

    response = service.evaluate(
        ConfidenceRequest(
            request_id="req-confidence-001",
            image_input=ImageConfidenceInput(
                model_confidence=0.91,
                affected_area=1280.5,
                polygon_count=2,
            ),
            text_input=TextConfidenceInput(
                retrieved_source_count=3,
                average_retrieval_score=0.74,
                has_rag_summary=True,
            ),
            workflow_input=WorkflowConfidenceInput(
                model_exists=True,
                training_triggered=False,
                error_count=0,
                status="completed",
            ),
        )
    )

    assert response.success is True
    assert response.result is not None
    assert 0.0 <= response.result.final_confidence <= 1.0
    assert response.result.final_label in {"high", "medium", "low"}
    assert response.result.image_confidence.label in {"high", "medium", "low"}
    assert response.result.text_confidence.label in {"high", "medium", "low"}
    assert response.result.workflow_confidence.label in {"high", "medium", "low"}


def test_confidence_service_penalizes_suspicious_full_positive_mask(
    tmp_path: Path,
) -> None:
    mask_path = tmp_path / "suspicious_mask.png"
    Image.fromarray(np.full((16, 16), 255, dtype=np.uint8)).save(mask_path)

    service = ConfidenceService()
    response = service.evaluate(
        ConfidenceRequest(
            request_id="req-confidence-002",
            image_input=ImageConfidenceInput(
                model_confidence=0.94,
                affected_area=256.0,
                polygon_count=1,
                mask_uri=str(mask_path),
                task_type="baldness_detection",
            ),
            text_input=TextConfidenceInput(
                retrieved_source_count=2,
                average_retrieval_score=0.81,
                has_rag_summary=True,
            ),
            workflow_input=WorkflowConfidenceInput(
                model_exists=True,
                training_triggered=False,
                error_count=0,
                status="completed",
            ),
        )
    )

    assert response.success is True
    assert response.result is not None
    assert response.result.image_confidence.score <= 0.5
    assert response.result.image_confidence.label == "low"
    assert any(
        "near-total" in warning for warning in response.result.image_confidence.warnings
    )
