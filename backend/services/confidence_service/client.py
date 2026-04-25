"""Local orchestrator client for the confidence service."""

from __future__ import annotations

import logging

from services.confidence_service.config import (
    ConfidenceServiceConfig,
    get_confidence_service_config,
)
from services.confidence_service.schemas import (
    ConfidenceRequest,
    ImageConfidenceInput,
    TextConfidenceInput,
    WorkflowConfidenceInput,
)
from services.confidence_service.service import ConfidenceService
from shared.schemas.service_results import ConfidenceServiceResult

logger = logging.getLogger(__name__)


class ConfidenceServiceClientError(Exception):
    """Raised when local confidence evaluation cannot be completed."""


class LocalConfidenceServiceClient:
    """Run the local confidence service from orchestrator synchronous code."""

    def __init__(
        self,
        *,
        config: ConfidenceServiceConfig | None = None,
        service: ConfidenceService | None = None,
    ) -> None:
        self._config = config or get_confidence_service_config()
        self._service = service or ConfidenceService(config=self._config)

    def evaluate(
        self,
        *,
        request_id: str,
        inference_result: dict | None,
        rag_result: dict | None,
        report_result: dict | None,
        training_triggered: bool,
        model_exists: bool,
        status: str,
        error_count: int,
        task_type: str | None = None,
    ) -> ConfidenceServiceResult:
        """Evaluate confidence and normalize the response for orchestrator use."""
        logger.info("local_confidence_execution_started | request_id=%s", request_id)
        request = ConfidenceRequest(
            request_id=request_id,
            image_input=ImageConfidenceInput(
                model_confidence=float(inference_result.get("confidence", 0.0))
                if inference_result
                else 0.0,
                affected_area=float(inference_result.get("affected_area", 0.0))
                if inference_result
                else 0.0,
                polygon_count=len(inference_result.get("polygons", []))
                if inference_result
                else 0,
                mask_uri=str(inference_result.get("mask_uri", "")) if inference_result else None,
                task_type=task_type,
            ),
            text_input=TextConfidenceInput(
                retrieved_source_count=len(rag_result.get("sources", [])) if rag_result else 0,
                average_retrieval_score=self._average_retrieval_score(rag_result),
                has_rag_summary=bool(rag_result and rag_result.get("summary")),
            ),
            workflow_input=WorkflowConfidenceInput(
                model_exists=model_exists,
                training_triggered=training_triggered,
                error_count=error_count,
                status=status,
            ),
        )
        response = self._service.evaluate(request)
        if not response.success or response.result is None:
            raise ConfidenceServiceClientError(response.message)

        logger.info(
            "local_confidence_execution_succeeded | request_id=%s | final_confidence=%.4f",
            request_id,
            response.result.final_confidence,
        )
        return ConfidenceServiceResult(
            image_confidence=response.result.image_confidence.score,
            text_confidence=response.result.text_confidence.score,
            workflow_confidence=response.result.workflow_confidence.score,
            final_confidence=response.result.final_confidence,
            final_label=response.result.final_label,
            explanation=response.result.explanation,
            image_detail=response.result.image_confidence.model_dump(),
            text_detail=response.result.text_confidence.model_dump(),
            workflow_detail=response.result.workflow_confidence.model_dump(),
            report_available=report_result is not None,
        )

    @staticmethod
    def _average_retrieval_score(rag_result: dict | None) -> float:
        if rag_result is None:
            return 0.0
        scores = [
            float(item.get("score", 0.0))
            for item in rag_result.get("results", [])
            if isinstance(item, dict)
        ]
        if not scores:
            return 0.0
        return sum(scores) / len(scores)
