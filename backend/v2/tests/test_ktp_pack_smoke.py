from __future__ import annotations

from shared.schemas.service_results import (
    ConfidenceServiceResult,
    InferenceServiceResult,
    ModelRegistryResult,
    RagServiceResult,
    ReportServiceResult,
    TrainingTriggerResult,
    VisualizationServiceResult,
)
from v2.adapters.python_services.ktp_services import KtpExecutionContext
from v2.adapters.python_services.ktp_rag import KtpKnowledgeAdapter
from v2.tools.handlers import (
    build_ktp_build_report_handler,
    build_ktp_build_visualization_handler,
    build_ktp_evaluate_confidence_handler,
    build_ktp_lookup_model_registry_handler,
    build_ktp_retrieve_knowledge_handler,
    build_ktp_run_inference_workflow_handler,
    build_ktp_trigger_training_handler,
)
from v2.tools.registry import build_default_tool_registry


class _FakeRagClient:
    def run_rag(
        self,
        *,
        request_id: str | None,
        user_query: str,
        task_type: str | None,
        region: str | None,
        crop_type: str | None,
        inference_result: dict | None = None,
        context: dict | None = None,
        top_k: int | None = None,
    ) -> RagServiceResult:
        del request_id, task_type, region, crop_type, inference_result, context
        return RagServiceResult(
            query=user_query,
            summary="NDVI emphasizes vegetation greenness, while EVI is more robust to canopy saturation and atmosphere.",
            sources=["demo-source-1"],
            top_k=top_k or 3,
            results=[{"chunk_id": "chunk-1", "text": "demo text"}],
        )


class _FakeKtpServiceBundle:
    def create_context(
        self,
        *,
        query: str,
        region: str = "henan",
        crop_type: str = "wheat",
        task_type: str = "crop_health_detection",
        request_id: str | None = None,
        use_mock_backend: bool = True,
        image_path: str | None = None,
        top_k: int = 3,
        extra_params: dict[str, object] | None = None,
    ) -> KtpExecutionContext:
        return KtpExecutionContext(
            request_id=request_id or "ktp-fake-001",
            query=query,
            region=region,
            crop_type=crop_type,
            task_type=task_type,
            use_mock_backend=use_mock_backend,
            image_path=image_path,
            top_k=top_k,
            extra_params=extra_params or {},
        )

    def ensure_model_lookup(self, context: KtpExecutionContext) -> ModelRegistryResult:
        context.model_lookup_backend = "fake"
        context.model_registry_result = ModelRegistryResult(
            model_exists=True,
            model_id=11,
            model_name="fake-ktp-model",
            model_version="1.2.3",
            artifact_uri="mock://models/fake-ktp-model/1.2.3",
            status="ready",
        )
        return context.model_registry_result

    def ensure_inference(self, context: KtpExecutionContext) -> InferenceServiceResult:
        self.ensure_model_lookup(context)
        context.inference_backend = "fake"
        context.inference_result = InferenceServiceResult(
            mask_uri="mock://inference/mask.tif",
            affected_area=123.4,
            confidence=0.88,
            model_version="1.2.3",
            model_name="fake-ktp-model",
            artifact_uri="mock://models/fake-ktp-model/1.2.3",
            polygons=[],
        )
        return context.inference_result

    def ensure_training(self, context: KtpExecutionContext) -> TrainingTriggerResult:
        context.training_backend = "fake"
        context.training_result = TrainingTriggerResult(
            training_triggered=True,
            training_job_id="train-fake-001",
            backend="fake",
        )
        return context.training_result

    def ensure_knowledge(self, context: KtpExecutionContext) -> RagServiceResult:
        context.rag_backend = "fake"
        context.rag_result = RagServiceResult(
            query=context.query,
            summary="fake knowledge summary",
            sources=["fake-source-1"],
            top_k=context.top_k,
            results=[{"chunk_id": "chunk-1", "text": "fake text"}],
        )
        return context.rag_result

    def ensure_confidence(self, context: KtpExecutionContext) -> ConfidenceServiceResult:
        self.ensure_inference(context)
        self.ensure_knowledge(context)
        context.confidence_backend = "fake"
        context.confidence_result = ConfidenceServiceResult(
            image_confidence=0.81,
            text_confidence=0.73,
            workflow_confidence=0.9,
            final_confidence=0.84,
            final_label="high",
            explanation="fake confidence",
        )
        return context.confidence_result

    def ensure_report(self, context: KtpExecutionContext) -> ReportServiceResult:
        self.ensure_confidence(context)
        context.report_backend = "fake"
        context.report_result = ReportServiceResult(
            report_uri="mock://reports/fake-report.html",
            title="fake ktp report",
            sections=["summary", "inference", "confidence"],
            report_id="report-fake-001",
        )
        return context.report_result

    def ensure_visualization(self, context: KtpExecutionContext) -> VisualizationServiceResult:
        self.ensure_report(context)
        context.visualization_backend = "fake"
        context.visualization_result = VisualizationServiceResult(
            visualization_uri="mock://visualizations/fake-dashboard.html",
            title="fake ktp dashboard",
            sections=["overview", "timeline", "artifacts"],
            visualization_id="viz-fake-001",
            artifacts=[],
        )
        return context.visualization_result


def test_ktp_retrieve_knowledge_handler_returns_observation_and_artifact() -> None:
    adapter = KtpKnowledgeAdapter(client=_FakeRagClient())
    handler = build_ktp_retrieve_knowledge_handler(adapter=adapter)

    observation, artifacts = handler(query="NDVI 和 EVI 有什么区别？", top_k=2)

    assert observation.source == "ktp.retrieve_knowledge"
    assert observation.status == "success"
    assert observation.payload["result_count"] == 1
    assert artifacts[0].pack_name == "ktp"
    assert artifacts[0].artifact_type == "knowledge_card"


def test_ktp_handlers_emit_structured_observations_for_pack_tools() -> None:
    bundle = _FakeKtpServiceBundle()

    lookup_observation, lookup_artifacts = build_ktp_lookup_model_registry_handler(bundle=bundle)(
        query="lookup model registry"
    )
    inference_observation, inference_artifacts = build_ktp_run_inference_workflow_handler(bundle=bundle)(
        query="run inference"
    )
    training_observation, training_artifacts = build_ktp_trigger_training_handler(bundle=bundle)(
        query="trigger training"
    )
    confidence_observation, confidence_artifacts = build_ktp_evaluate_confidence_handler(bundle=bundle)(
        query="evaluate confidence"
    )
    report_observation, report_artifacts = build_ktp_build_report_handler(bundle=bundle)(
        query="build report"
    )
    visualization_observation, visualization_artifacts = build_ktp_build_visualization_handler(bundle=bundle)(
        query="build visualization"
    )

    assert lookup_observation.source == "ktp.lookup_model_registry"
    assert lookup_artifacts[0].artifact_type == "registry_card"

    assert inference_observation.source == "ktp.run_inference_workflow"
    assert inference_artifacts[0].artifact_type == "inference_card"

    assert training_observation.source == "ktp.trigger_training"
    assert training_artifacts[0].artifact_type == "training_card"

    assert confidence_observation.source == "ktp.evaluate_confidence"
    assert confidence_artifacts[0].artifact_type == "confidence_card"

    assert report_observation.source == "ktp.build_report"
    assert report_artifacts[0].artifact_type == "report_card"

    assert visualization_observation.source == "ktp.build_visualization"
    assert visualization_artifacts[0].artifact_type == "visualization_card"
    assert visualization_observation.payload["visualization_result"]["visualization_id"] == "viz-fake-001"


def test_default_tool_registry_contains_expanded_ktp_tools() -> None:
    registry = build_default_tool_registry(ktp_knowledge_adapter=KtpKnowledgeAdapter(client=_FakeRagClient()))
    tool_names = {tool.name for tool in registry.list_tools()}
    assert "ktp.retrieve_knowledge" in tool_names
    assert "ktp.lookup_model_registry" in tool_names
    assert "ktp.run_inference_workflow" in tool_names
    assert "ktp.trigger_training" in tool_names
    assert "ktp.build_report" in tool_names
    assert "ktp.evaluate_confidence" in tool_names
    assert "ktp.build_visualization" in tool_names
