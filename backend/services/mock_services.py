"""Fallback service adapters providing default/mock responses when real services are unavailable."""

from __future__ import annotations

import logging

from shared.schemas.service_results import (
    ConfidenceServiceResult,
    InferenceServiceResult,
    ModelRegistryResult,
    RagServiceResult,
    ReportServiceResult,
    TrainingTriggerResult,
    VisualizationServiceResult,
)
from shared.presentation import display_region, display_crop_type, display_task_type

logger = logging.getLogger(__name__)


class MockModelRegistryService:
    """Placeholder model registry lookup service."""

    _catalog = {
        ("crop_health_detection", "henan", "wheat"): (
            "wheat-health-segmentation",
            "1.2.0",
        ),
        ("crop_health_detection", "heilongjiang", "rice"): (
            "rice-stress-segmentation",
            "0.9.1",
        ),
        ("yield_estimation", "anhui", "rice"): (
            "rice-yield-estimator",
            "2.0.0",
        ),
    }

    def lookup(
        self,
        task_type: str | None,
        region: str | None,
        crop_type: str | None,
    ) -> ModelRegistryResult:
        """Return a deterministic mock registry lookup result."""
        logger.info(
            "model_registry_lookup_started | task_type=%s | region=%s | crop_type=%s",
            task_type,
            region,
            crop_type,
        )
        model = self._catalog.get((task_type, region, crop_type))
        if model is None:
            result = ModelRegistryResult(
                model_exists=False,
                reason=(
                    "no ready model found for "
                    f"region={region} crop_type={crop_type} task_type={task_type}"
                ),
            )
        else:
            result = ModelRegistryResult(
                model_exists=True,
                model_id=1,
                model_name=model[0],
                model_version=model[1],
                artifact_uri=f"mock://models/{model[0]}/{model[1]}",
                status="ready",
            )
        logger.info(
            "model_registry_lookup_succeeded | model_exists=%s",
            result.model_exists,
        )
        return result


class MockTrainingService:
    """Placeholder training trigger service."""

    def trigger_training(
        self,
        request_id: str,
        task_type: str | None,
        region: str | None,
        crop_type: str | None,
        extra_params: dict | None = None,
    ) -> TrainingTriggerResult:
        """Return a deterministic mock training trigger result."""
        logger.info("training_trigger_started | request_id=%s", request_id)
        suffix = "-".join(part for part in [task_type, region, crop_type] if part) or "generic"
        result = TrainingTriggerResult(
            training_triggered=True,
            training_job_id=f"train-{request_id[:8]}-{suffix}",
            workflow_id=None,
            run_id=None,
            task_queue=None,
            backend="mock",
        )
        logger.info("training_trigger_succeeded | request_id=%s", request_id)
        return result


class MockInferenceService:
    """Placeholder inference service."""

    def run_inference(
        self,
        request_id: str,
        task_type: str | None,
        region: str | None,
        crop_type: str | None,
        model_name: str | None,
        model_version: str | None,
        image_path: str | None = None,
        use_mock: bool | None = None,
        extra_params: dict | None = None,
    ) -> InferenceServiceResult:
        """Return a deterministic mock inference result."""
        logger.info("inference_started | request_id=%s", request_id)
        affected_area = 1280.5 if crop_type == "wheat" else 960.0
        result = InferenceServiceResult(
            mask_uri=f"mock://inference/{request_id}/mask.tif",
            affected_area=affected_area,
            confidence=0.91,
            model_version=model_version or "unknown",
            model_name=model_name,
            artifact_uri=f"mock://models/{model_name or 'unknown'}",
            polygons=[],
        )
        logger.info(
            "inference_succeeded | request_id=%s | model_name=%s | task_type=%s | region=%s | image_path=%s | use_mock=%s",
            request_id,
            model_name,
            task_type,
            region,
            image_path,
            use_mock,
        )
        return result


class MockRagService:
    """Placeholder retrieval-augmented generation service."""

    def run_rag(
        self,
        request_id: str | None,
        user_query: str,
        task_type: str | None,
        region: str | None,
        crop_type: str | None,
        inference_result: dict | None = None,
        context: dict | None = None,
        top_k: int | None = None,
    ) -> RagServiceResult:
        """Return a deterministic mock RAG result."""
        logger.info(
            "rag_started | request_id=%s | task_type=%s | region=%s",
            request_id,
            task_type,
            region,
        )
        sources = [
            "mock://knowledge/agronomy-guide",
            "mock://knowledge/remote-sensing-playbook",
            "mock://knowledge/risk-factors",
        ]
        result = RagServiceResult(
            query=user_query,
            summary=(
                f"Mock agronomic context for {crop_type or 'unknown crop'} in "
                f"{region or 'unknown region'} responding to: {user_query}"
            ),
            sources=sources,
            top_k=top_k or 3,
            results=[
                {
                    "chunk_id": f"mock-chunk-{index}",
                    "document_id": f"mock-document-{index}",
                    "text": f"Mock chunk {index} for {crop_type or 'unknown crop'} in {region or 'unknown region'}.",
                    "source": source,
                    "score": round(0.9 - (index * 0.05), 4),
                    "metadata": {
                        "task_type": task_type,
                        "region": region,
                        "crop_type": crop_type,
                        "context": context or {},
                        "has_inference_result": inference_result is not None,
                    },
                }
                for index, source in enumerate(sources[: top_k or 3], start=1)
            ],
        )
        logger.info(
            "rag_succeeded | request_id=%s | task_type=%s | region=%s",
            request_id,
            task_type,
            region,
        )
        return result


class MockReportService:
    """Placeholder report rendering service."""

    def build_report(
        self,
        request_id: str,
        task_type: str | None,
        region: str | None,
        crop_type: str | None,
        user_query: str | None,
        inference_result: dict | None,
        rag_result: dict | None,
        confidence_result: dict | None = None,
        training_triggered: bool = False,
    ) -> ReportServiceResult:
        """Return a deterministic mock report result."""
        logger.info("report_build_started | request_id=%s", request_id)
        sections = [
            "请求摘要",
            "模型或训练结果",
            "知识上下文",
            "置信度快照",
        ]
        if inference_result is None:
            sections.insert(1, "训练触发摘要")
        if rag_result is None:
            sections.remove("知识上下文")
        task_label = display_task_type(task_type, default="分析", include_raw=False)
        context_parts = [
            part
            for part in (
                display_region(region, default="", include_raw=False),
                display_crop_type(crop_type, default="", include_raw=False),
            )
            if part
        ]
        report_title = f"{task_label}报告（{' / '.join(context_parts)}）" if context_parts else f"{task_label}报告"
        result = ReportServiceResult(
            report_uri=f"mock://reports/{request_id}.json",
            title=report_title,
            sections=sections,
            report_id=f"mock-report-{request_id}",
            html=None,
            generated_at=None,
        )
        logger.info("report_build_succeeded | request_id=%s", request_id)
        return result


class MockConfidenceService:
    """Placeholder confidence evaluation service."""

    def evaluate(
        self,
        request_id: str,
        inference_result: dict | None,
        rag_result: dict | None,
        report_result: dict | None,
        training_triggered: bool,
        model_exists: bool,
        status: str,
        error_count: int,
    ) -> ConfidenceServiceResult:
        """Return a deterministic mock confidence result."""
        logger.info("confidence_evaluation_started")
        image_confidence = float(inference_result["confidence"]) if inference_result else 0.0
        workflow_confidence = 0.72 if training_triggered else 0.9
        if not model_exists:
            workflow_confidence -= 0.05
        if status != "completed":
            workflow_confidence -= 0.04
        workflow_confidence -= min(0.2, error_count * 0.05)
        if rag_result is None:
            workflow_confidence -= 0.05
        if report_result is None:
            workflow_confidence -= 0.03
        final_confidence = round((image_confidence + workflow_confidence) / 2, 2)
        result = ConfidenceServiceResult(
            image_confidence=image_confidence,
            text_confidence=float(min(len(rag_result.get("sources", [])) * 0.2, 1.0)) if rag_result else 0.0,
            workflow_confidence=round(workflow_confidence, 2),
            final_confidence=final_confidence,
            final_label="high" if final_confidence >= 0.8 else "medium" if final_confidence >= 0.55 else "low",
            explanation=(
                "Mock 工作流置信度综合了模型输出置信度、"
                "工作流完整性以及是否需要训练。"
            ),
            image_detail={},
            text_detail={},
            workflow_detail={},
            report_available=report_result is not None,
        )
        logger.info("confidence_evaluation_succeeded")
        return result


class MockVisualizationService:
    """Placeholder workflow visualization service."""

    def build_visualization(
        self,
        *,
        request_id: str,
        workflow_status: str,
        **_: object,
    ) -> VisualizationServiceResult:
        """Return a deterministic mock dashboard result."""
        logger.info("visualization_generation_started | request_id=%s", request_id)
        result = VisualizationServiceResult(
            visualization_uri=f"mock://visualizations/{request_id}/dashboard.html",
            title=f"工作流仪表盘 ({request_id[:8]})",
            sections=["overview", "timeline", "artifacts"],
            visualization_id=f"mock-viz-{request_id}",
            artifact_dir=f"mock://visualizations/{request_id}/artifacts",
            snapshot_path=f"mock://visualizations/{request_id}/workflow_snapshot.json",
            html=None,
            generated_at=None,
            artifacts=[],
        )
        logger.info(
            "visualization_generation_succeeded | request_id=%s | status=%s",
            request_id,
            workflow_status,
        )
        return result
