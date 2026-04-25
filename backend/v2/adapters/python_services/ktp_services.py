from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import uuid4

from services.mock_services import (
    MockConfidenceService,
    MockInferenceService,
    MockModelRegistryService,
    MockRagService,
    MockReportService,
    MockTrainingService,
    MockVisualizationService,
)
from services.rag_service.client import RAGServiceClientError
from shared.config.settings import Settings, get_settings
from shared.schemas.service_results import (
    ConfidenceServiceResult,
    InferenceServiceResult,
    ModelRegistryResult,
    RagServiceResult,
    ReportServiceResult,
    TrainingTriggerResult,
    VisualizationServiceResult,
)
from v2.adapters.python_services.ktp_rag import (
    KtpKnowledgeAdapter,
    build_default_ktp_knowledge_adapter,
)

if TYPE_CHECKING:
    from services.confidence_service.client import LocalConfidenceServiceClient
    from services.inference_service.client import LocalInferenceServiceClient
    from services.model_registry.local_client import LocalModelRegistryLookupClient
    from services.report_service.client import LocalReportServiceClient
    from services.training_service.local_client import LocalTrainingServiceClient
    from services.visualization_service.client import LocalVisualizationServiceClient


KTP_DEFAULT_REGION = "henan"
KTP_DEFAULT_CROP_TYPE = "wheat"
KTP_DEFAULT_TASK_TYPE = "crop_health_detection"


def _get_defaults():
    try:
        from shared.config.settings import get_settings
        s = get_settings()
        return s.ktp_default_region, s.ktp_default_crop_type, s.ktp_default_task_type
    except Exception:
        return KTP_DEFAULT_REGION, KTP_DEFAULT_CROP_TYPE, KTP_DEFAULT_TASK_TYPE


class KtpServiceError(RuntimeError):
    """Raised when the real KTP service path cannot complete successfully."""


@dataclass(slots=True)
class KtpExecutionContext:
    request_id: str
    query: str
    region: str
    crop_type: str
    task_type: str
    use_mock_backend: bool = False
    image_path: str | None = None
    top_k: int = 3
    extra_params: dict[str, object] = field(default_factory=dict)
    backend_notes: list[str] = field(default_factory=list)
    model_lookup_backend: str | None = None
    inference_backend: str | None = None
    rag_backend: str | None = None
    training_backend: str | None = None
    report_backend: str | None = None
    confidence_backend: str | None = None
    visualization_backend: str | None = None
    model_registry_result: ModelRegistryResult | None = None
    inference_result: InferenceServiceResult | None = None
    rag_result: RagServiceResult | None = None
    training_result: TrainingTriggerResult | None = None
    report_result: ReportServiceResult | None = None
    confidence_result: ConfidenceServiceResult | None = None
    visualization_result: VisualizationServiceResult | None = None


@dataclass(slots=True)
class KtpServiceBundle:
    settings: Settings = field(default_factory=get_settings)
    knowledge_adapter: KtpKnowledgeAdapter = field(default_factory=build_default_ktp_knowledge_adapter)
    mock_model_registry: MockModelRegistryService = field(default_factory=MockModelRegistryService)
    mock_inference: MockInferenceService = field(default_factory=MockInferenceService)
    mock_rag: MockRagService = field(default_factory=MockRagService)
    mock_training: MockTrainingService = field(default_factory=MockTrainingService)
    mock_report: MockReportService = field(default_factory=MockReportService)
    mock_confidence: MockConfidenceService = field(default_factory=MockConfidenceService)
    mock_visualization: MockVisualizationService = field(default_factory=MockVisualizationService)
    _real_model_registry_client: LocalModelRegistryLookupClient | None = field(default=None, init=False)
    _real_inference_client: LocalInferenceServiceClient | None = field(default=None, init=False)
    _real_training_client: LocalTrainingServiceClient | None = field(default=None, init=False)
    _real_report_client: LocalReportServiceClient | None = field(default=None, init=False)
    _real_confidence_client: LocalConfidenceServiceClient | None = field(default=None, init=False)
    _real_visualization_client: LocalVisualizationServiceClient | None = field(default=None, init=False)

    def create_context(
        self,
        *,
        query: str,
        region: str = KTP_DEFAULT_REGION,
        crop_type: str = KTP_DEFAULT_CROP_TYPE,
        task_type: str = KTP_DEFAULT_TASK_TYPE,
        request_id: str | None = None,
        use_mock_backend: bool = False,
        image_path: str | None = None,
        top_k: int = 3,
        extra_params: dict[str, object] | None = None,
    ) -> KtpExecutionContext:
        return KtpExecutionContext(
            request_id=request_id or self._new_request_id(),
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
        if context.model_registry_result is not None:
            return context.model_registry_result

        if context.use_mock_backend:
            result = self.mock_model_registry.lookup(
                task_type=context.task_type,
                region=context.region,
                crop_type=context.crop_type,
            )
            context.model_registry_result = result
            context.model_lookup_backend = "mock"
            context.backend_notes.append("模型注册查询使用了模拟目录（演示稳定性）。")
            return result

        try:
            client = self._get_real_model_registry_client()
            lookup = client.lookup_model(
                region=context.region,
                crop_type=context.crop_type,
                task_type=context.task_type,
            )
            result = ModelRegistryResult(
                model_exists=lookup.model_exists,
                model_id=lookup.model_id,
                model_name=lookup.model_name,
                model_version=lookup.model_version,
                artifact_uri=lookup.artifact_uri,
                status=lookup.status.value if lookup.status is not None else None,
                reason=lookup.reason,
            )
            context.model_registry_result = result
            context.model_lookup_backend = "real"
            return result
        except Exception as exc:
            raise KtpServiceError(f"KTP model registry lookup failed: {exc}") from exc

    def ensure_inference(self, context: KtpExecutionContext) -> InferenceServiceResult:
        if context.inference_result is not None:
            return context.inference_result

        if context.task_type == "baldness_detection" and not context.image_path:
            context.inference_result = InferenceServiceResult(
                mask_uri="",
                affected_area=0.0,
                confidence=0.0,
                model_version="n/a",
                model_name=None,
                artifact_uri=None,
            )
            context.inference_backend = "skipped"
            context.backend_notes.append("斑秃检测已跳过：未提供图像路径。")
            return context.inference_result

        if context.task_type == "lai_inversion":
            context.model_lookup_backend = "lai_prosail"
            context.backend_notes.append("LAI 反演跳过模型注册，使用 PROSAIL 后端。")
            from services.inference_service.service import InferenceService
            from services.inference_service.schemas import InferenceRequest
            inf_service = InferenceService()
            req = InferenceRequest(
                request_id=context.request_id,
                region=context.region or "lai",
                crop_type=context.crop_type or "lai",
                task_type=context.task_type,
                image_path=None,
                use_mock=False,
                extra_params=context.extra_params or {},
            )
            try:
                asyncio.get_running_loop()
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    result = pool.submit(asyncio.run, inf_service.run_inference(req)).result()
            except RuntimeError:
                result = asyncio.run(inf_service.run_inference(req))
            lai_val = result.result.get("lai") if result.result else None
            conf_val = result.result.get("confidence") if result.result else None
            context.inference_result = InferenceServiceResult(
                mask_uri="",
                affected_area=float(lai_val) if lai_val is not None else 0.0,
                confidence=float(conf_val) if conf_val is not None else 0.0,
                model_version="prosail-lut",
                model_name="PROSAIL",
                artifact_uri=None,
            )
            context.inference_backend = "lai_prosail"
            return context.inference_result

        lookup = self.ensure_model_lookup(context)
        if context.use_mock_backend:
            result = self.mock_inference.run_inference(
                request_id=context.request_id,
                task_type=context.task_type,
                region=context.region,
                crop_type=context.crop_type,
                model_name=lookup.model_name,
                model_version=lookup.model_version,
                image_path=context.image_path,
                use_mock=True,
                extra_params=context.extra_params,
            )
            context.inference_result = result
            context.inference_backend = "mock"
            context.backend_notes.append("推理工作流使用了模拟预测器。")
            return result

        if not lookup.model_exists:
            raise KtpServiceError(
                lookup.reason
                or (
                    "KTP model registry does not contain a ready model for "
                    f"{context.region}/{context.crop_type}/{context.task_type}."
                )
            )

        try:
            client = self._get_real_inference_client()
            result = client.run_inference(
                request_id=context.request_id,
                region=context.region,
                crop_type=context.crop_type,
                task_type=context.task_type,
                image_path=context.image_path,
                use_mock=False,
                extra_params=context.extra_params,
                model_name=lookup.model_name,
                model_version=lookup.model_version,
            )
            context.inference_result = result
            context.inference_backend = "real"
            return result
        except Exception as exc:
            raise KtpServiceError(f"KTP inference workflow failed: {exc}") from exc

    def ensure_knowledge(self, context: KtpExecutionContext) -> RagServiceResult:
        if context.rag_result is not None:
            return context.rag_result

        if context.use_mock_backend:
            result = self.mock_rag.run_rag(
                request_id=context.request_id,
                user_query=context.query,
                task_type=context.task_type,
                region=context.region,
                crop_type=context.crop_type,
                inference_result=context.inference_result.model_dump(mode="json")
                if context.inference_result is not None
                else None,
                context=context.extra_params,
                top_k=context.top_k,
            )
            context.rag_result = result
            context.rag_backend = "mock"
            context.backend_notes.append("知识检索使用了模拟知识服务。")
            return result

        try:
            result = self.knowledge_adapter.retrieve_knowledge(
                query=context.query,
                top_k=context.top_k,
            )
            context.rag_result = result
            context.rag_backend = "real"
            return result
        except RAGServiceClientError as exc:
            raise KtpServiceError(f"KTP knowledge retrieval failed: {exc}") from exc

    def ensure_training(self, context: KtpExecutionContext) -> TrainingTriggerResult:
        if context.training_result is not None:
            return context.training_result

        if context.use_mock_backend:
            result = self.mock_training.trigger_training(
                request_id=context.request_id,
                task_type=context.task_type,
                region=context.region,
                crop_type=context.crop_type,
                extra_params=context.extra_params,
            )
            context.training_result = result
            context.training_backend = "mock"
            context.backend_notes.append("训练触发使用了模拟后端（演示稳定性）。")
            return result

        try:
            client = self._get_real_training_client()
            result = client.trigger_training(
                request_id=context.request_id,
                task_type=context.task_type,
                region=context.region,
                crop_type=context.crop_type,
                extra_params=context.extra_params,
            )
            context.training_result = result
            context.training_backend = result.backend or "real"
            return result
        except Exception as exc:
            raise KtpServiceError(f"KTP training trigger failed: {exc}") from exc

    def ensure_confidence(self, context: KtpExecutionContext) -> ConfidenceServiceResult:
        if context.confidence_result is not None:
            return context.confidence_result

        inference = self.ensure_inference(context)
        rag = self._get_or_maybe_load_knowledge(context)

        if context.use_mock_backend:
            result = self.mock_confidence.evaluate(
                request_id=context.request_id,
                inference_result=inference.model_dump(mode="json"),
                rag_result=rag.model_dump(mode="json") if rag is not None else None,
                report_result=context.report_result.model_dump(mode="json")
                if context.report_result is not None
                else None,
                training_triggered=context.training_result is not None,
                model_exists=bool(self.ensure_model_lookup(context).model_exists),
                status="completed",
                error_count=0,
            )
            context.confidence_result = result
            context.confidence_backend = "mock"
            context.backend_notes.append("置信度评估使用了模拟评分器。")
            return result

        try:
            client = self._get_real_confidence_client()
            result = client.evaluate(
                request_id=context.request_id,
                inference_result=inference.model_dump(mode="json"),
                rag_result=rag.model_dump(mode="json") if rag is not None else None,
                report_result=context.report_result.model_dump(mode="json")
                if context.report_result is not None
                else None,
                training_triggered=context.training_result is not None,
                model_exists=bool(self.ensure_model_lookup(context).model_exists),
                status="completed",
                error_count=0,
                task_type=context.task_type,
            )
            context.confidence_result = result
            context.confidence_backend = "real"
            return result
        except Exception as exc:
            raise KtpServiceError(f"KTP confidence evaluation failed: {exc}") from exc

    def ensure_report(self, context: KtpExecutionContext) -> ReportServiceResult:
        if context.report_result is not None:
            return context.report_result

        inference = self.ensure_inference(context)
        rag = self._get_or_maybe_load_knowledge(context)

        if context.use_mock_backend:
            result = self.mock_report.build_report(
                request_id=context.request_id,
                task_type=context.task_type,
                region=context.region,
                crop_type=context.crop_type,
                user_query=context.query,
                inference_result=inference.model_dump(mode="json"),
                rag_result=rag.model_dump(mode="json") if rag is not None else None,
                confidence_result=context.confidence_result.model_dump(mode="json")
                if context.confidence_result is not None
                else None,
                training_triggered=context.training_result is not None,
            )
            context.report_result = result
            context.report_backend = "mock"
            context.backend_notes.append("报告生成使用了模拟渲染器。")
            return result

        try:
            client = self._get_real_report_client()
            result = client.build_report(
                request_id=context.request_id,
                task_type=context.task_type,
                region=context.region,
                crop_type=context.crop_type,
                user_query=context.query,
                inference_result=inference.model_dump(mode="json"),
                rag_result=rag.model_dump(mode="json") if rag is not None else None,
                confidence_result=context.confidence_result.model_dump(mode="json")
                if context.confidence_result is not None
                else None,
                training_triggered=context.training_result is not None,
            )
            context.report_result = result
            context.report_backend = "real"
            return result
        except Exception as exc:
            raise KtpServiceError(f"KTP report generation failed: {exc}") from exc

    def ensure_visualization(self, context: KtpExecutionContext) -> VisualizationServiceResult:
        if context.visualization_result is not None:
            return context.visualization_result

        inference = self.ensure_inference(context)
        rag = self._get_or_maybe_load_knowledge(context)
        report = self.ensure_report(context)
        confidence = self.ensure_confidence(context)
        lookup = self.ensure_model_lookup(context)

        if context.use_mock_backend:
            result = self.mock_visualization.build_visualization(
                request_id=context.request_id,
                workflow_status="completed",
            )
            context.visualization_result = result
            context.visualization_backend = "mock"
            context.backend_notes.append("可视化生成使用了模拟仪表盘。")
            return result

        try:
            client = self._get_real_visualization_client()
            result = client.build_visualization(
                request_id=context.request_id,
                workflow_status="completed",
                user_query=context.query,
                task_type=context.task_type,
                region=context.region,
                crop_type=context.crop_type,
                image_path=context.image_path,
                use_mock=context.use_mock_backend,
                model_exists=lookup.model_exists,
                model_id=lookup.model_id,
                model_name=lookup.model_name,
                model_version=lookup.model_version,
                model_status=lookup.status,
                artifact_uri=lookup.artifact_uri,
                inference_result=inference.model_dump(mode="json"),
                rag_result=rag.model_dump(mode="json") if rag is not None else None,
                report_result=report.model_dump(mode="json"),
                confidence_result=confidence.model_dump(mode="json"),
                training_triggered=context.training_result is not None,
                training_job_id=context.training_result.training_job_id
                if context.training_result is not None
                else None,
                training_workflow_id=context.training_result.workflow_id
                if context.training_result is not None
                else None,
                training_run_id=context.training_result.run_id
                if context.training_result is not None
                else None,
                training_task_queue=context.training_result.task_queue
                if context.training_result is not None
                else None,
                training_backend=context.training_result.backend
                if context.training_result is not None
                else None,
                final_state={
                    "request_id": context.request_id,
                    "query": context.query,
                    "backend_notes": context.backend_notes,
                },
            )
            context.visualization_result = result
            context.visualization_backend = "real"
            return result
        except Exception as exc:
            raise KtpServiceError(f"KTP visualization generation failed: {exc}") from exc

    def _get_or_maybe_load_knowledge(self, context: KtpExecutionContext) -> RagServiceResult | None:
        if context.rag_result is not None:
            return context.rag_result
        if bool(context.extra_params.get("include_knowledge")):
            return self.ensure_knowledge(context)
        return None

    def _get_real_model_registry_client(self) -> LocalModelRegistryLookupClient:
        if self._real_model_registry_client is None:
            from services.model_registry.local_client import LocalModelRegistryLookupClient

            self._real_model_registry_client = LocalModelRegistryLookupClient(
                database_url=self.settings.database_url
            )
        return self._real_model_registry_client

    def _get_real_inference_client(self) -> LocalInferenceServiceClient:
        if self._real_inference_client is None:
            from services.inference_service.client import LocalInferenceServiceClient

            self._real_inference_client = LocalInferenceServiceClient(
                database_url=self.settings.database_url
            )
        return self._real_inference_client

    def _get_real_training_client(self) -> LocalTrainingServiceClient:
        if self._real_training_client is None:
            from services.training_service.local_client import LocalTrainingServiceClient

            self._real_training_client = LocalTrainingServiceClient()
        return self._real_training_client

    def _get_real_report_client(self) -> LocalReportServiceClient:
        if self._real_report_client is None:
            from services.report_service.client import LocalReportServiceClient

            self._real_report_client = LocalReportServiceClient()
        return self._real_report_client

    def _get_real_confidence_client(self) -> LocalConfidenceServiceClient:
        if self._real_confidence_client is None:
            from services.confidence_service.client import LocalConfidenceServiceClient

            self._real_confidence_client = LocalConfidenceServiceClient()
        return self._real_confidence_client

    def _get_real_visualization_client(self) -> LocalVisualizationServiceClient:
        if self._real_visualization_client is None:
            from services.visualization_service.client import LocalVisualizationServiceClient

            self._real_visualization_client = LocalVisualizationServiceClient()
        return self._real_visualization_client

    @staticmethod
    def _new_request_id() -> str:
        return f"ktp-{uuid4().hex[:10]}"


def build_default_ktp_service_bundle() -> KtpServiceBundle:
    return KtpServiceBundle()
