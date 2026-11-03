"""Single implementation of the workflow summary report.

The report is a pure projection of workflow state: it reads the stored step
results, builds the operator-facing sections, registers the report artifact, and
links it back to the workflow. The workflow completion path, the historical
backfill path, and the registered tool all call this module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from runtime.artifact_store import ArtifactStore
from runtime.workflow_reports import register_map_report
from schemas.analysis_workflow import AnalysisWorkflowSummary

WORKFLOW_REPORT_TOOL_NAME = "remote_sensing.workflow_report"
ARTIFACT_KIND = "workflow_summary_report"

STEP_LABELS = {
    "imagery": "影像准备",
    "crop": "农作物识别",
    "lai": "PROSAIL/LAI",
    "growth": "长势观测",
    "potential": "遥感冠层指数",
    "yield_simple": "自动简化估产（试验）",
    "yield": "APSIM 估产",
}


def generate_workflow_report(
    *,
    workflow: AnalysisWorkflowSummary,
    artifact_root: Path,
    artifacts: ArtifactStore,
    status: str | None = None,
) -> dict[str, str]:
    """Render and register the summary report; return its artifact references."""
    labels = STEP_LABELS
    sections: list[dict[str, Any]] = []
    if workflow.data_mode == "demo":
        sections.append({"title": "模拟数据 · 仅用于功能演示", "rows": [["数据来源", "构造的生长曲线与产量示例"]],
                         "notes": ["未运行 APSIM，未读取地块影像、气象或土壤，不代表实际产量。"]})
    sections.append({"title": "实际生效参数", "rows": [
        ["影像准备分辨率 m", workflow.parameters["target_resolution_m"]],
        ["共享反射率波段", " / ".join(workflow.parameters["reflectance_bands"])],
        ["影像准备参数来源", "算法固定配置"],
    ]})
    for step in workflow.steps:
        result = step.result or {}
        rows = [["状态", step.status], ["说明", step.detail]]
        if step.step_id == "crop":
            prediction = result.get("predicted_class") or {}
            decision = result.get("crop_decision") or {}
            if decision:
                rows += [["最终判定", decision.get("final_name_zh")],
                         ["判定来源", {"llm": "大模型结合地点与时序判定", "user_confirmed": "用户确认",
                                       "model_fallback": "大模型不可用，回退模型最高分"}.get(decision.get("source"), "—")],
                         ["判定依据", decision.get("rationale")]]
            rows += [["最高类别", prediction.get("name_zh")], ["模型分数", prediction.get("score")]]
        elif step.step_id == "lai":
            rows += [["LAI 均值", result.get("lai_mean")],
                     ["有效覆盖率", (result.get("quality") or {}).get("valid_pixel_fraction")]]
            scene = result.get("scene_parameters") or {}
            application = result.get("constraint_application") or {}
            if scene:
                rows += [["场景参数来源", "用户编辑并确认" if scene.get("source") == "user_confirmed" else "大模型自动配置" if scene.get("source") == "llm" else "规则回退"],
                         ["配置依据", scene.get("reasoning")],
                         ["范围生效状态", {"applied": "已生效", "fallback": "回退完整 LUT", "unconstrained": "完整 LUT"}.get(application.get("status"), "待核验")]]
                for key, label in (("lai_range", "LAI"), ("cab_range", "Cab"), ("lidfa_range", "叶倾角"), ("psoil_range", "土壤参数")):
                    rows.append([f"{label} 生效范围", str(application.get("effective", {}).get(key, "完整 LUT"))])
                if application.get("reason"):
                    rows.append(["回退原因", application["reason"]])
        elif step.step_id == "growth":
            rows += [["植被比例", result.get("vegetation_ratio")]]
        elif step.step_id == "potential":
            rows += [["冠层指数（未校准）", result.get("canopy_index")]]
        elif step.step_id == "yield":
            rows += ([["APSIM 示例模拟单产 t/ha", result.get("example_yield_t_ha")], ["示例模板", (result.get("input_provenance") or {}).get("template")], ["配套气象", (result.get("input_provenance") or {}).get("weather")]] if workflow.data_mode == "apsim_example" else [["APSIM LAI 约束产量 t/ha", result.get("constrained_yield_t_ha")]])
        elif step.step_id == "yield_simple":
            rows += [["粮食干重试验估计 t/ha", result.get("estimated_yield_t_ha")],
                     ["遥感有效生长期", f"{(result.get('season') or {}).get('start', '—')} 至 {(result.get('season') or {}).get('end', '—')}"],
                     ["本地实收校准", "尚未校准"]]
        notes = []
        if step.step_id == "crop":
            notes = list(result.get("warnings") or [])
            if result.get("crop_decision"):
                notes.append("最终判定含大模型先验，未经实地验证；模型分数未经校准。")
        if step.step_id in {"growth", "potential", "yield_simple", "yield"}:
            notes = [str(result[key]) for key in ("warning", "uncertainty_note") if result.get(key)]
        assessment = result.get("input_assessment") or {}
        notes += [issue.get("message", "") for issue in assessment.get("issues", [])]
        sections.append({"title": labels[step.step_id],
                         "rows": [[label, value if value is not None else "—"] for label, value in rows],
                         "notes": notes})
    return register_map_report(
        artifacts, run_id=workflow.workflow_id,
        output_dir=artifact_root / "workflows" / workflow.workflow_id / "summary",
        kind=ARTIFACT_KIND,
        title="估产模拟演示工作流总报告" if workflow.data_mode == "demo" else "地块影像分析工作流总报告",
        context={"工作流 ID": workflow.workflow_id, "状态": status or workflow.status,
                 "选区面积": f"{workflow.aoi.area_hectares:.2f} ha",
                 "影像 ID": workflow.imagery_item_id,
                 "观测日期": workflow.imagery_snapshot.acquired_at[:10],
                 "用户选择任务": "、".join(workflow.requested_task_ids)},
        sections=sections,
        highlights=[{"label": "已完成任务", "value": str(sum(step.status == "completed" for step in workflow.steps if step.step_id != "imagery"))},
                    {"label": "待补充任务", "value": str(sum(step.status == "blocked" for step in workflow.steps))},
                    {"label": "失败任务", "value": str(sum(step.status == "failed" for step in workflow.steps))},
                    {"label": "用户选择任务", "value": str(len(workflow.requested_task_ids))}],
        visuals=[{"type": "statuses", "title": "各任务执行状态",
                  "items": [{"label": labels[step.step_id], "state": step.status} for step in workflow.steps]}],
    )


def write_workflow_report(
    *,
    workflows: Any,
    workflow_id: str,
    owner_id: str,
    artifact_root: Path,
    artifacts: ArtifactStore,
    status: str | None = None,
) -> dict[str, str] | None:
    """Load the workflow, generate its summary report, and link it back."""
    workflow = workflows.get(workflow_id, owner_id=owner_id)
    if workflow is None:
        return None
    references = generate_workflow_report(
        workflow=workflow,
        artifact_root=artifact_root,
        artifacts=artifacts,
        status=status,
    )
    workflows.set_report(workflow_id, owner_id=owner_id, references=references)
    return references
