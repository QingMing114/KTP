"""Local orchestrator client for the report service."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from shared.presentation import (
    display_crop_type,
    display_region,
    display_task_type,
    localize_runtime_text,
)
from services.report_service.config import (
    ReportServiceConfig,
    get_report_service_config,
)
from services.report_service.schemas import (
    ReportInputConfidence,
    ReportInputInference,
    ReportInputRAG,
    ReportInputSummary,
    ReportRequest,
)
from services.report_service.service import ReportService
from shared.inference_sanity import MaskSanityResult, inspect_mask_artifact
from shared.schemas.service_results import ReportServiceResult

logger = logging.getLogger(__name__)


class ReportServiceClientError(Exception):
    """Raised when local report generation cannot be completed."""


class LocalReportServiceClient:
    """Run the local report service from orchestrator synchronous code."""

    def __init__(
        self,
        *,
        config: ReportServiceConfig | None = None,
        service: ReportService | None = None,
    ) -> None:
        self._config = config or get_report_service_config()
        self._service = service or ReportService(config=self._config)

    def build_report(
        self,
        *,
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
        """Generate a report and normalize the output for orchestrator use."""
        logger.info("local_report_execution_started | request_id=%s", request_id)
        mask_sanity = self._inspect_inference_mask(inference_result)
        report_request = ReportRequest(
            request_id=request_id,
            title=self._build_title(task_type=task_type, region=region, crop_type=crop_type),
            user_query=user_query or "",
            region=region,
            crop_type=crop_type,
            task_type=task_type,
            summary=self._build_summary(
                inference_result=inference_result,
                rag_result=rag_result,
                training_triggered=training_triggered,
                mask_sanity=mask_sanity,
            ),
            inference=self._build_inference_section(
                inference_result,
                mask_sanity=mask_sanity,
            ),
            rag=self._build_rag_section(rag_result),
            confidence=self._build_confidence_section(confidence_result),
            extra_metadata={
                "training_triggered": training_triggered,
                "class_distribution": inference_result.get("class_distribution", []) if inference_result else [],
                "class_labels": inference_result.get("class_labels", {}) if inference_result else {},
                "target_classes": inference_result.get("target_classes", []) if inference_result else [],
            },
        )
        response = self._service.generate_report(report_request)
        if not response.success or response.result is None:
            raise ReportServiceClientError(response.message)

        logger.info(
            "local_report_execution_succeeded | request_id=%s | report_path=%s",
            request_id,
            response.result.report_path,
        )
        generated_at = response.result.generated_at
        return ReportServiceResult(
            report_uri=response.result.report_path,
            title=response.result.report_title,
            sections=response.result.sections,
            report_id=response.result.report_id,
            html=response.result.html,
            generated_at=generated_at.isoformat()
            if isinstance(generated_at, datetime)
            else str(generated_at),
        )

    @staticmethod
    def _build_title(
        *,
        task_type: str | None,
        region: str | None,
        crop_type: str | None,
    ) -> str:
        task_label = display_task_type(task_type, default="分析", include_raw=False)
        context_parts = [
            part
            for part in (
                display_region(region, default="", include_raw=False),
                display_crop_type(crop_type, default="", include_raw=False),
            )
            if part
        ]
        if context_parts:
            return f"{task_label}报告（{' / '.join(context_parts)}）"
        return f"{task_label}报告"

    @staticmethod
    def _build_summary(
        *,
        inference_result: dict | None,
        rag_result: dict | None,
        training_triggered: bool,
        mask_sanity: MaskSanityResult | None,
    ) -> ReportInputSummary:
        key_findings: list[str] = []
        if inference_result is not None:
            key_findings.append(
                f"推理已完成，置信度为 {inference_result.get('confidence', 0.0)}。"
            )
        if mask_sanity is not None and mask_sanity.warnings:
            key_findings.append(f"推理结果告警：{localize_runtime_text(mask_sanity.summary)}。")
        if training_triggered:
            key_findings.append("由于不存在可用模型，已触发训练工作流。")
        if rag_result and rag_result.get("sources"):
            key_findings.append(
                f"已检索到 {len(rag_result.get('sources', []))} 条支撑知识来源。"
            )
        overview = (
            "该报告由编排流程输出自动生成。"
            if inference_result is not None
            else "该报告由无即时推理结果的流程分支自动生成。"
        )
        return ReportInputSummary(overview=overview, key_findings=key_findings)

    @staticmethod
    def _build_inference_section(
        inference_result: dict | None,
        *,
        mask_sanity: MaskSanityResult | None,
    ) -> ReportInputInference | None:
        if inference_result is None:
            return None
        return ReportInputInference(
            model_name=str(inference_result.get("model_name", "未知模型")),
            model_version=str(inference_result.get("model_version", "未知版本")),
            affected_area=float(inference_result.get("affected_area", 0.0)),
            confidence=float(inference_result.get("confidence", 0.0)),
            mask_uri=str(inference_result.get("mask_uri", "")),
            polygons=list(inference_result.get("polygons", [])),
            positive_ratio=mask_sanity.positive_ratio if mask_sanity else None,
            warnings=[localize_runtime_text(item) for item in mask_sanity.warnings]
            if mask_sanity
            else [],
        )

    @staticmethod
    def _build_rag_section(rag_result: dict | None) -> ReportInputRAG | None:
        if rag_result is None:
            return None
        return ReportInputRAG(
            summary=localize_runtime_text(str(rag_result.get("summary", ""))),
            sources=[str(source) for source in rag_result.get("sources", [])],
            results=list(rag_result.get("results", [])),
        )

    @staticmethod
    def _build_confidence_section(
        confidence_result: dict | None,
    ) -> ReportInputConfidence | None:
        if confidence_result is None:
            return None
        return ReportInputConfidence(
            image_confidence=float(confidence_result.get("image_confidence", 0.0)),
            text_confidence=float(confidence_result.get("text_confidence", 0.0)),
            workflow_confidence=float(confidence_result.get("workflow_confidence", 0.0)),
            final_confidence=float(confidence_result.get("final_confidence", 0.0)),
            final_label=str(confidence_result.get("final_label", "low")),
            explanation=str(confidence_result.get("explanation", "")),
            warnings=[
                localize_runtime_text(str(warning))
                for warning in confidence_result.get("image_detail", {}).get("warnings", [])
            ],
        )

    @staticmethod
    def _inspect_inference_mask(inference_result: dict | None) -> MaskSanityResult | None:
        if inference_result is None:
            return None
        mask_uri = str(inference_result.get("mask_uri", "")).strip()
        if not mask_uri:
            return None
        return inspect_mask_artifact(mask_uri)
