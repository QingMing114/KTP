"""Registered tool wrapper for the workflow summary report.

Report generation is a pure projection of stored workflow state: it never
re-runs algorithms. It stays host-invoked because the caller supplies the
workflow owner, and because the workflow entry decides when a report is due.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field

from runtime.artifact_store import ArtifactStore
from runtime.workflow_report import (
    ARTIFACT_KIND,
    WORKFLOW_REPORT_TOOL_NAME,
    write_workflow_report,
)
from schemas.runtime import ObservationV2, PackArtifactView, ToolPresentation, ToolSpecV2

WORKFLOW_REPORT_TOOL_DISPLAY_NAME = "分析报告"

ProgressCallback = Callable[[str, int], None]


class WorkflowReportToolInput(BaseModel):
    """JSON input for the workflow report tool."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    status: str | None = None


def _presentation() -> ToolPresentation:
    return ToolPresentation(
        card_kind="report",
        summary_fields=["report_uri", "report_kind"],
        progress_phases=["汇总任务结果", "生成报告", "登记产物"],
        result_renderer="workflow_report",
    )


def build_workflow_report_tool_spec(
    *,
    available: bool,
    unavailable_reason: str | None = None,
    model_visible: bool = False,
) -> ToolSpecV2:
    """Build the tool spec; ``model_visible`` is the visibility gate."""
    return ToolSpecV2(
        name=WORKFLOW_REPORT_TOOL_NAME,
        display_name=WORKFLOW_REPORT_TOOL_DISPLAY_NAME,
        description=(
            "把已完成工作流各步骤的结果汇总为面向用户的分析报告并登记产物；"
            "只读取已保存结果，不重新运行算法。"
        ),
        visibility="bounded",
        category="remote_sensing",
        usage_hint=(
            "当工作流结束、或历史工作流报告缺失/版本过期需要重算时使用；"
            "没有已完成步骤时不要调用。"
        ),
        input_schema=WorkflowReportToolInput.model_json_schema(),
        output_schema={
            "type": "object",
            "properties": {
                "report_uri": {"type": "string"},
                "report_title": {"type": "string"},
            },
        },
        safety_level="safe",
        surface_visibility="all" if model_visible else "debug",
        enabled_by_default=True,
        permissions=["artifact:write"],
        produces_artifacts=[ARTIFACT_KIND],
        availability="available" if available else "unavailable",
        unavailable_reason=None
        if available
        else (unavailable_reason or "workflow report tool is not configured"),
        presentation=_presentation(),
    )


def build_workflow_report_handler(
    *,
    workflow_store_resolver: Callable[[], Any],
    artifact_store: ArtifactStore,
    artifact_root: Path,
) -> Callable[..., tuple[ObservationV2, list[PackArtifactView]]]:
    """Bind the report implementation to the workflow store and artifact root."""

    def handler(
        *,
        progress_callback: ProgressCallback | None = None,
        **tool_input: Any,
    ) -> tuple[ObservationV2, list[PackArtifactView]]:
        payload = WorkflowReportToolInput.model_validate(tool_input)
        workflows = workflow_store_resolver()
        if workflows is None:
            raise RuntimeError("workflow report tool requires the workflow store")
        if progress_callback is not None:
            progress_callback("正在汇总任务结果", 30)
        references = write_workflow_report(
            workflows=workflows,
            workflow_id=payload.run_id,
            owner_id=payload.owner_id,
            artifact_root=artifact_root,
            artifacts=artifact_store,
            status=payload.status,
        )
        if references is None:
            raise RuntimeError(f"workflow {payload.run_id!r} was not found")
        if progress_callback is not None:
            progress_callback("报告已生成并登记", 100)
        observation = ObservationV2(
            source=WORKFLOW_REPORT_TOOL_NAME,
            status="success",
            summary=f"分析报告已生成：{payload.run_id}",
            payload={"run_id": payload.run_id, **references},
        )
        return observation, []

    return handler


def configure_workflow_report_tool(
    registry: Any,
    *,
    workflow_store_resolver: Callable[[], Any],
    artifact_store: ArtifactStore,
    artifact_root: Path,
    model_visible: bool = False,
) -> None:
    """(Re)register the report tool on the host registry."""
    registry.register(
        WORKFLOW_REPORT_TOOL_NAME,
        build_workflow_report_tool_spec(available=True, model_visible=model_visible),
        build_workflow_report_handler(
            workflow_store_resolver=workflow_store_resolver,
            artifact_store=artifact_store,
            artifact_root=artifact_root,
        ),
    )


def register_unavailable_workflow_report_tool(
    registry: Any, *, reason: str | None = None
) -> None:
    """Register the spec so discovery and availability reporting stay honest."""
    registry.register(
        WORKFLOW_REPORT_TOOL_NAME,
        build_workflow_report_tool_spec(available=False, unavailable_reason=reason),
        _unavailable_handler,
    )


def _unavailable_handler(**_kwargs: Any) -> tuple[ObservationV2, list[PackArtifactView]]:
    raise RuntimeError("workflow report tool is not configured")
