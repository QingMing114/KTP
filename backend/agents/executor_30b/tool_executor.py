"""Mock tool executor that dispatches to service adapter placeholders."""

from __future__ import annotations

import logging

from services.inference_service.client import (
    InferenceServiceClientError,
    LocalInferenceServiceClient,
)
from services.mock_services import (
    MockConfidenceService,
    MockInferenceService,
    MockRagService,
    MockReportService,
    MockTrainingService,
    MockVisualizationService,
)
from services.confidence_service.client import (
    ConfidenceServiceClientError,
    LocalConfidenceServiceClient,
)
from services.rag_service.client import LocalRAGServiceClient, RAGServiceClientError
from services.report_service.client import LocalReportServiceClient, ReportServiceClientError
from services.training_service.client import TrainingServiceClientError
from services.training_service.local_client import LocalTrainingServiceClient
from services.visualization_service.client import (
    LocalVisualizationServiceClient,
    VisualizationServiceClientError,
)
from shared.schemas.executor import ExecutorTaskInput, ExecutorTaskOutput

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Dispatch structured executor tasks to service adapter placeholders."""

    def __init__(
        self,
        *,
        training_service: MockTrainingService | LocalTrainingServiceClient | None = None,
        inference_service: MockInferenceService | LocalInferenceServiceClient | None = None,
        rag_service: MockRagService | LocalRAGServiceClient | None = None,
        report_service: MockReportService | LocalReportServiceClient | None = None,
        confidence_service: MockConfidenceService | LocalConfidenceServiceClient | None = None,
        visualization_service: MockVisualizationService | LocalVisualizationServiceClient | None = None,
    ) -> None:
        self._training_service = training_service or MockTrainingService()
        self._inference_service = inference_service or MockInferenceService()
        self._rag_service = rag_service or MockRagService()
        self._report_service = report_service or MockReportService()
        self._confidence_service = confidence_service or MockConfidenceService()
        self._visualization_service = visualization_service or MockVisualizationService()

    def execute(self, task: ExecutorTaskInput) -> ExecutorTaskOutput:
        """Execute a tool task and return a structured result."""
        logger.info(
            "tool_executor_started | request_id=%s | tool_name=%s",
            task.request_id,
            task.tool_name,
        )
        handler = {
            "trigger_training": self._run_training,
            "run_inference": self._run_inference,
            "run_rag": self._run_rag,
            "build_report": self._build_report,
            "evaluate_confidence": self._evaluate_confidence,
            "build_visualization": self._build_visualization,
        }.get(task.tool_name)
        if handler is None:
            raise ValueError(f"Unsupported tool: {task.tool_name}")

        result = handler(task)
        logger.info(
            "tool_executor_succeeded | request_id=%s | tool_name=%s",
            task.request_id,
            task.tool_name,
        )
        return result

    def _run_training(self, task: ExecutorTaskInput) -> ExecutorTaskOutput:
        try:
            result = self._training_service.trigger_training(
                request_id=task.request_id,
                task_type=task.payload.get("task_type"),
                region=task.payload.get("region"),
                crop_type=task.payload.get("crop_type"),
                extra_params=task.payload.get("extra_params"),
            )
        except TrainingServiceClientError as exc:
            logger.warning(
                "tool_executor_training_failed | request_id=%s | detail=%s",
                task.request_id,
                str(exc),
            )
            return ExecutorTaskOutput(
                request_id=task.request_id,
                tool_name=task.tool_name,
                success=False,
                message=str(exc),
                output={},
            )
        return ExecutorTaskOutput(
            request_id=task.request_id,
            tool_name=task.tool_name,
            success=True,
            message="Training workflow triggered.",
            output=result.model_dump(),
        )

    def _run_inference(self, task: ExecutorTaskInput) -> ExecutorTaskOutput:
        try:
            result = self._inference_service.run_inference(
                request_id=task.request_id,
                task_type=task.payload.get("task_type"),
                region=task.payload.get("region"),
                crop_type=task.payload.get("crop_type"),
                model_name=task.payload.get("model_name"),
                model_version=task.payload.get("model_version"),
                image_path=task.payload.get("image_path"),
                use_mock=task.payload.get("use_mock"),
                extra_params=task.payload.get("extra_params"),
            )
        except InferenceServiceClientError as exc:
            logger.warning(
                "tool_executor_inference_failed | request_id=%s | detail=%s",
                task.request_id,
                str(exc),
            )
            return ExecutorTaskOutput(
                request_id=task.request_id,
                tool_name=task.tool_name,
                success=False,
                message=str(exc),
                output={},
            )
        return ExecutorTaskOutput(
            request_id=task.request_id,
            tool_name=task.tool_name,
            success=True,
            message="Inference completed.",
            output=result.model_dump(),
        )

    def _run_rag(self, task: ExecutorTaskInput) -> ExecutorTaskOutput:
        try:
            result = self._rag_service.run_rag(
                request_id=task.request_id,
                user_query=str(task.payload.get("user_query", "")),
                task_type=task.payload.get("task_type"),
                region=task.payload.get("region"),
                crop_type=task.payload.get("crop_type"),
                inference_result=task.payload.get("inference_result"),
                context=task.payload.get("context"),
                top_k=task.payload.get("top_k"),
            )
        except RAGServiceClientError as exc:
            logger.warning(
                "tool_executor_rag_failed | request_id=%s | detail=%s",
                task.request_id,
                str(exc),
            )
            return ExecutorTaskOutput(
                request_id=task.request_id,
                tool_name=task.tool_name,
                success=False,
                message=str(exc),
                output={},
            )
        return ExecutorTaskOutput(
            request_id=task.request_id,
            tool_name=task.tool_name,
            success=True,
            message="RAG completed.",
            output=result.model_dump(),
        )

    def _build_report(self, task: ExecutorTaskInput) -> ExecutorTaskOutput:
        try:
            result = self._report_service.build_report(
                request_id=task.request_id,
                task_type=task.payload.get("task_type"),
                region=task.payload.get("region"),
                crop_type=task.payload.get("crop_type"),
                user_query=task.payload.get("user_query"),
                inference_result=task.payload.get("inference_result"),
                rag_result=task.payload.get("rag_result"),
                confidence_result=task.payload.get("confidence_result"),
                training_triggered=bool(task.payload.get("training_triggered", False)),
            )
        except ReportServiceClientError as exc:
            logger.warning(
                "tool_executor_report_failed | request_id=%s | detail=%s",
                task.request_id,
                str(exc),
            )
            return ExecutorTaskOutput(
                request_id=task.request_id,
                tool_name=task.tool_name,
                success=False,
                message=str(exc),
                output={},
            )
        return ExecutorTaskOutput(
            request_id=task.request_id,
            tool_name=task.tool_name,
            success=True,
            message="Report built.",
            output=result.model_dump(),
        )

    def _evaluate_confidence(self, task: ExecutorTaskInput) -> ExecutorTaskOutput:
        try:
            result = self._confidence_service.evaluate(
                request_id=task.request_id,
                inference_result=task.payload.get("inference_result"),
                rag_result=task.payload.get("rag_result"),
                report_result=task.payload.get("report_result"),
                training_triggered=bool(task.payload.get("training_triggered", False)),
                model_exists=bool(task.payload.get("model_exists", False)),
                status=str(task.payload.get("status", "completed")),
                error_count=int(task.payload.get("error_count", 0)),
                task_type=task.payload.get("task_type"),
            )
        except ConfidenceServiceClientError as exc:
            logger.warning(
                "tool_executor_confidence_failed | request_id=%s | detail=%s",
                task.request_id,
                str(exc),
            )
            return ExecutorTaskOutput(
                request_id=task.request_id,
                tool_name=task.tool_name,
                success=False,
                message=str(exc),
                output={},
            )
        return ExecutorTaskOutput(
            request_id=task.request_id,
            tool_name=task.tool_name,
            success=True,
            message="Confidence evaluation completed.",
            output=result.model_dump(),
        )

    def _build_visualization(self, task: ExecutorTaskInput) -> ExecutorTaskOutput:
        try:
            result = self._visualization_service.build_visualization(
                request_id=task.request_id,
                workflow_status=str(task.payload.get("workflow_status", "completed")),
                user_query=str(task.payload.get("user_query", "")),
                task_type=task.payload.get("task_type"),
                region=task.payload.get("region"),
                crop_type=task.payload.get("crop_type"),
                image_path=task.payload.get("image_path"),
                use_mock=task.payload.get("use_mock"),
                extra_params=task.payload.get("extra_params") or {},
                planner_result=task.payload.get("planner_result"),
                executor_result=task.payload.get("executor_result"),
                model_exists=task.payload.get("model_exists"),
                model_id=task.payload.get("model_id"),
                model_name=task.payload.get("model_name"),
                model_version=task.payload.get("model_version"),
                model_status=task.payload.get("model_status"),
                artifact_uri=task.payload.get("artifact_uri"),
                model_metrics=task.payload.get("model_metrics"),
                model_description=task.payload.get("model_description"),
                training_triggered=bool(task.payload.get("training_triggered", False)),
                training_job_id=task.payload.get("training_job_id"),
                training_workflow_id=task.payload.get("training_workflow_id"),
                training_run_id=task.payload.get("training_run_id"),
                training_task_queue=task.payload.get("training_task_queue"),
                training_backend=task.payload.get("training_backend"),
                inference_result=task.payload.get("inference_result"),
                rag_result=task.payload.get("rag_result"),
                report_result=task.payload.get("report_result"),
                confidence_result=task.payload.get("confidence_result"),
                stage_timings=list(task.payload.get("stage_timings", [])),
                errors=list(task.payload.get("errors", [])),
                final_state=task.payload.get("final_state") or {},
            )
        except VisualizationServiceClientError as exc:
            logger.warning(
                "tool_executor_visualization_failed | request_id=%s | detail=%s",
                task.request_id,
                str(exc),
            )
            return ExecutorTaskOutput(
                request_id=task.request_id,
                tool_name=task.tool_name,
                success=False,
                message=str(exc),
                output={},
            )
        return ExecutorTaskOutput(
            request_id=task.request_id,
            tool_name=task.tool_name,
            success=True,
            message="Visualization built.",
            output=result.model_dump(),
        )
