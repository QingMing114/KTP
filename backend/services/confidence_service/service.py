"""Business service for structured confidence evaluation."""

from __future__ import annotations

import logging

from services.confidence_service.config import (
    ConfidenceServiceConfig,
    get_confidence_service_config,
)
from services.confidence_service.fusion import fuse_confidence_results
from services.confidence_service.image_confidence import score_image_confidence
from services.confidence_service.schemas import ConfidenceRequest, ConfidenceResponse
from services.confidence_service.text_confidence import score_text_confidence
from services.confidence_service.workflow_confidence import score_workflow_confidence

logger = logging.getLogger(__name__)


class ConfidenceService:
    """Evaluate image, text, and workflow confidence and fuse the result."""

    def __init__(self, config: ConfidenceServiceConfig | None = None) -> None:
        self._config = config or get_confidence_service_config()

    def evaluate(self, request: ConfidenceRequest) -> ConfidenceResponse:
        """Evaluate confidence for a structured workflow result."""
        logger.info("confidence_evaluation_started | request_id=%s", request.request_id)
        try:
            image_result = score_image_confidence(request.image_input)
            text_result = score_text_confidence(request.text_input)
            workflow_result = score_workflow_confidence(request.workflow_input)
            final_result = fuse_confidence_results(
                image_result=image_result,
                text_result=text_result,
                workflow_result=workflow_result,
                config=self._config,
            )
        except Exception as exc:
            logger.exception(
                "confidence_evaluation_failed | request_id=%s",
                request.request_id,
            )
            return ConfidenceResponse(
                request_id=request.request_id,
                success=False,
                result=None,
                message=f"confidence evaluation failed: {exc}",
            )

        logger.info(
            "confidence_evaluation_succeeded | request_id=%s | final_confidence=%.4f",
            request.request_id,
            final_result.final_confidence,
        )
        return ConfidenceResponse(
            request_id=request.request_id,
            success=True,
            result=final_result,
            message="confidence evaluated",
        )

    def get_health_snapshot(self) -> dict[str, str]:
        """Return a health snapshot for the confidence service."""
        return {
            "image_weight": str(self._config.image_confidence_weight),
            "text_weight": str(self._config.text_confidence_weight),
            "workflow_weight": str(self._config.workflow_confidence_weight),
        }
