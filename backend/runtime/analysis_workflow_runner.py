"""Execute crop and PROSAIL/LAI steps from one verified AOI reflectance image."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from infra.imagery.aoi_band_reader import AoiBandReadError, read_prosail_reflectance_aoi
from infra.imagery.crop_spatial import CropInferenceError
from runtime.analysis_workflow_store import AnalysisWorkflowStore
from runtime.artifact_store import ArtifactStore
from runtime.crop_analysis_store import CropAnalysisStore
from runtime.crop_classification import CropImagerySource, classify_crop, crop_step_detail
from runtime.crop_decision import resolve_crop_class
from runtime.lai_analysis_store import LaiAnalysisStore
from runtime.yield_input_assessment import assess_yield_inputs
from runtime.apsim_field_runner import ApsimFieldError, run_field_yield
from runtime.apsim_example import ApsimExampleError, run_example, register_example_report
from runtime.yield_potential import YieldPotentialError, estimate_yield_potential
from runtime.simple_yield import SimpleYieldError
from runtime.simple_yield_runner import run_simple_yield
from runtime.yield_demo import run_yield_demo, register_yield_demo_report
from runtime.lai_quality import assess_lai_raster_quality
from runtime.workspace_lai import configure_workspace_lai
from runtime.professional_review import create_review
from schemas.runtime import SceneParameters
from runtime.workflow_reports import (
    REPORT_VERSION, register_crop_report, register_growth_report, register_map_report,
    register_potential_report, register_result_json, register_yield_report, register_simple_yield_report,
)
from schemas.analysis_workflow import AnalysisWorkflowSummary
from schemas.workspace import WorkspaceIntent
from schemas.spatial import CreateCropAnalysisRequest, CreateLaiAnalysisRequest
from v2.tools.lai_report_handler import run_lai_html_report

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _provenance(workflow: AnalysisWorkflowSummary) -> dict[str, Any]:
    snapshot = workflow.imagery_snapshot
    return {
        "item_id": snapshot.item_id,
        "collection": snapshot.collection,
        "acquired_at": snapshot.acquired_at,
        "cloud_cover": snapshot.cloud_cover,
        "coverage_percent": snapshot.coverage_percent,
        "platform": snapshot.platform,
        "item_version": snapshot.item_version,
        "asset_fingerprint": snapshot.asset_fingerprint,
    }


def run_analysis_workflow(
    workflow_id: str,
    *,
    owner_id: str,
    selected_item: Any,
    artifact_root: Path,
    workflows: AnalysisWorkflowStore,
    crops: CropAnalysisStore,
    lais: LaiAnalysisStore,
    artifacts: ArtifactStore,
    make_lai_result: Callable[..., dict],
    run_task_ids: set[str],
    llm_provider: Any = None,
) -> None:
    """Keep independent task failures while sharing one image download."""
    workflow = workflows.get(workflow_id, owner_id=owner_id)
    if workflow is None:
        raise KeyError(workflow_id)
    if workflow.data_mode == "demo":
        run_yield_demo(workflow, workflows=workflows, artifacts=artifacts, artifact_root=artifact_root)
        _write_workflow_summary_report(workflows, workflow_id, owner_id, artifact_root, artifacts, status="completed")
        workflows.update_status(workflow_id, owner_id=owner_id, status="completed", detail="估产模拟演示已完成，结果及 APSIM 模板报告可查看")
        return
    root = artifact_root / "workflows" / workflow_id
    root.mkdir(parents=True, exist_ok=True)
    reflectance = root / "reflectance.tif"
    image_step = next(step for step in workflow.steps if step.step_id == "imagery")
    try:
        if image_step.status != "completed" or not reflectance.is_file():
            workflows.update_step(workflow_id, "imagery", owner_id=owner_id,
                                  status="running", progress_percent=2, detail="正在读取 Sentinel 波段")

            def image_progress(detail: str, percent: int) -> None:
                workflows.update_step(workflow_id, "imagery", owner_id=owner_id,
                                      status="running", progress_percent=percent, detail=detail)

            read_prosail_reflectance_aoi(
                item=selected_item, geometry=workflow.aoi.geometry.model_dump(mode="json"),
                output_path=reflectance, target_resolution_m=workflow.parameters["target_resolution_m"],
                progress_callback=image_progress,
            )
            artifact_id = artifacts.register(
                workflow_id,
                SimpleNamespace(pack_name="sentinel", artifact_type="reflectance_tif",
                                title="共享 AOI Sentinel 反射率", uri=str(reflectance), content=None),
            )
            workflows.update_step(workflow_id, "imagery", owner_id=owner_id,
                                  status="completed", progress_percent=100,
                                  detail="AOI 五波段影像已准备，可供作物识别和 LAI 共用",
                                  result={"artifact_id": artifact_id, "bands": ["B02", "B03", "B04", "B07", "B08"],
                                          "resolution_m": workflow.parameters["target_resolution_m"],
                                          "parameters": workflow.parameters, "imagery_provenance": _provenance(workflow)})
    except AoiBandReadError as exc:
        detail = str(exc)
        logger.warning("analysis_workflow_imagery_failed | workflow_id=%s", workflow_id)
        workflows.update_step(workflow_id, "imagery", owner_id=owner_id,
                              status="failed", detail=detail)
        for task in run_task_ids & {"crop", "lai"}:
            workflows.update_step(workflow_id, task, owner_id=owner_id,
                                  status="blocked", detail="共享影像准备失败，任务未启动")
        _finish(workflows, workflow_id, owner_id, artifact_root=artifact_root, artifacts=artifacts)
        return
    except Exception:
        logger.exception("analysis_workflow_imagery_failed | workflow_id=%s", workflow_id)
        workflows.update_step(workflow_id, "imagery", owner_id=owner_id,
                              status="failed", detail="影像准备失败，请稍后重试或更换影像。")
        for task in run_task_ids & {"crop", "lai"}:
            workflows.update_step(workflow_id, task, owner_id=owner_id,
                                  status="blocked", detail="共享影像准备失败，任务未启动")
        _finish(workflows, workflow_id, owner_id, artifact_root=artifact_root, artifacts=artifacts)
        return

    if "crop" in run_task_ids:
        if _run_crop(workflow, reflectance, root, workflows, crops, artifacts, owner_id, llm_provider):
            # Professional mode pauses before every dependent step.
            return
    if "lai" in run_task_ids:
        workflow = workflows.get(workflow_id, owner_id=owner_id) or workflow
        if workflow.professional_mode:
            step = next(s for s in workflow.steps if s.step_id == "lai")
            if not step.result.get("parameters_confirmed"):
                scene = step.result.get("scene_parameters") or configure_workspace_lai(workflow, reflectance, llm_provider)
                context = workflows.get_workspace(workflow.workspace_id, owner_id=owner_id)
                if context is None:
                    raise ValueError("专业模式缺少工作台输入快照")
                review = create_review(workflows, owner_id=owner_id, context=context,
                    intent=WorkspaceIntent(intent="execute", task_ids=workflow.requested_task_ids, summary="确认反演参数"),
                    run_id=workflow.run_id or workflow_id, conversation_id=workflow.conversation_id,
                    phase="lai", workflow=workflow, scene=scene)
                updated = workflows.update_step(workflow_id, "lai", owner_id=owner_id, status="blocked", progress_percent=0,
                    detail="场景参数已推荐，等待编辑并确认后执行 LAI 反演",
                    result={"scene_parameters": scene, "reason_code": "professional_confirmation_required", "review_id": review.review_id})
                step = next(s for s in updated.steps if s.step_id == "lai")
                workflows.finish_review(review.review_id, owner_id=owner_id, step_version=step.updated_at)
                workflows.update_status(workflow_id, owner_id=owner_id, status="blocked", detail="专业模式：请编辑并确认 LAI 参数后继续")
                return
        _run_lai(workflow, reflectance, root, workflows, lais, artifacts, make_lai_result, owner_id, llm_provider)
    _finish(workflows, workflow_id, owner_id, artifact_root=artifact_root, artifacts=artifacts)


def _run_crop(
    workflow: AnalysisWorkflowSummary, reflectance: Path, root: Path,
    workflows: AnalysisWorkflowStore, crops: CropAnalysisStore,
    artifacts: ArtifactStore, owner_id: str, llm_provider: Any = None,
) -> bool:
    """Run the crop step; return True when professional mode paused for a decision."""
    workflow_id = workflow.workflow_id
    child = crops.create(CreateCropAnalysisRequest(
        aoi=workflow.aoi, imagery_item_id=workflow.imagery_item_id,
        imagery_snapshot=workflow.imagery_snapshot, farm_id=workflow.farm_id,
    ), owner_id=owner_id)
    workflows.update_step(workflow_id, "crop", owner_id=owner_id, status="running",
                          analysis_id=child.analysis_id, progress_percent=5,
                          detail="正在执行作物识别")
    crops.update(child.analysis_id, status="running", stage="preparing", progress_percent=5,
                 detail="正在使用工作流共享影像")
    try:
        def progress(detail: str, percent: int) -> None:
            step_progress = min(95, max(5, percent))
            stage = "inference" if percent >= 90 else "preparing"
            crops.update(child.analysis_id, stage=stage, progress_percent=step_progress, detail=detail)
            workflows.update_step(workflow_id, "crop", owner_id=owner_id,
                                  status="running", progress_percent=step_progress, detail=detail)

        outcome = classify_crop(
            source=CropImagerySource(reflectance_path=reflectance),
            geometry=workflow.aoi.geometry.model_dump(mode="json"),
            observed_at=workflow.imagery_snapshot.acquired_at,
            farm_id=workflow.farm_id,
            area_hectares=workflow.aoi.area_hectares,
            output_dir=root / "crop",
            run_id=workflow_id,
            artifact_store=artifacts,
            imagery_item_id=workflow.imagery_item_id,
            provenance=_provenance(workflow),
            llm_provider=llm_provider,
            progress_callback=progress,
            decision_progress=("正在结合地点与时序先验判定作物", 97),
            extra_result_fields={"shared_imagery_workflow_id": workflow_id},
        )
        result = outcome.result
        decision = outcome.decision
        crops.update(child.analysis_id, status="completed", stage="completed",
                     progress_percent=100, detail="作物识别已完成", result=result, completed_at=_now())
        updated = workflows.update_step(workflow_id, "crop", owner_id=owner_id,
                                        status="completed", progress_percent=100,
                                        detail=crop_step_detail(decision), result=result)
        if not workflow.professional_mode or decision is None:
            return False
        context = workflows.get_workspace(workflow.workspace_id, owner_id=owner_id)
        if context is None:
            raise ValueError("专业模式缺少工作台输入快照")
        review = create_review(
            workflows, owner_id=owner_id, context=context,
            intent=WorkspaceIntent(intent="execute", task_ids=workflow.requested_task_ids,
                                   summary="确认农作物识别结果"),
            run_id=workflow.run_id or workflow_id, conversation_id=workflow.conversation_id,
            phase="crop", workflow=workflow, crop=decision,
        )
        updated = workflows.update_step(workflow_id, "crop", owner_id=owner_id,
                                        result={**result, "review_id": review.review_id})
        step = next(step for step in updated.steps if step.step_id == "crop")
        workflows.finish_review(review.review_id, owner_id=owner_id, step_version=step.updated_at)
        for dependent in ("lai", "growth", "potential", "yield_simple", "yield"):
            if any(candidate.step_id == dependent for candidate in updated.steps):
                workflows.update_step(workflow_id, dependent, owner_id=owner_id,
                                      status="blocked", detail="等待确认农作物识别结果")
        workflows.update_status(workflow_id, owner_id=owner_id, status="blocked",
                                detail="专业模式：请确认农作物识别结果后继续")
        return True
    except CropInferenceError as exc:
        detail = str(exc)
        logger.warning("analysis_workflow_crop_failed | workflow_id=%s", workflow_id)
        crops.update(child.analysis_id, status="failed", stage="failed", detail=detail,
                     result={"error": detail}, completed_at=_now())
        workflows.update_step(workflow_id, "crop", owner_id=owner_id,
                              status="failed", detail=detail, result={"error": detail})
        return False
    except Exception:
        logger.exception("analysis_workflow_crop_failed | workflow_id=%s", workflow_id)
        detail = "作物识别执行失败，请稍后重试。"
        crops.update(child.analysis_id, status="failed", stage="failed", detail=detail,
                     result={"error": detail}, completed_at=_now())
        workflows.update_step(workflow_id, "crop", owner_id=owner_id,
                              status="failed", detail=detail, result={"error": detail})
        return False


def _run_lai(
    workflow: AnalysisWorkflowSummary, reflectance: Path, root: Path,
    workflows: AnalysisWorkflowStore, lais: LaiAnalysisStore,
    artifacts: ArtifactStore, make_lai_result: Callable[..., dict], owner_id: str,
    llm_provider: Any = None,
) -> None:
    workflow_id = workflow.workflow_id
    child = lais.create(CreateLaiAnalysisRequest(
        aoi=workflow.aoi, imagery_item_id=workflow.imagery_item_id,
        imagery_snapshot=workflow.imagery_snapshot, farm_id=workflow.farm_id,
    ))
    workflows.update_step(workflow_id, "lai", owner_id=owner_id, status="running",
                          analysis_id=child.analysis_id, progress_percent=5,
                          detail="正在自动配置 LAI 场景参数")
    lais.update(child.analysis_id, status="running", stage="inversion", progress_percent=5,
                detail="正在使用工作流共享影像")
    last_progress = -1
    scene_data = {}
    try:
        previous = next(s for s in workflow.steps if s.step_id == "lai").result.get("scene_parameters")
        # Reuse the persisted proposal on retry instead of asking the model again.
        scene_data = previous or configure_workspace_lai(workflow, reflectance, llm_provider)
        constraints = SceneParameters.model_validate(scene_data).to_constraints()
        source_label = "用户确认" if scene_data["source"] == "user_confirmed" else "大模型" if scene_data["source"] == "llm" else "规则回退"
        workflows.update_step(workflow_id, "lai", owner_id=owner_id, status="running",
                              detail=f"{source_label}场景参数已生成，正在执行反演",
                              result={"scene_parameters": scene_data, "parameters_confirmed": workflow.professional_mode})
        def inversion_progress(processed: int, total: int) -> None:
            nonlocal last_progress
            percent = min(85, 10 + round(75 * processed / max(total, 1)))
            # Avoid a SQLite write per pixel while preserving meaningful progress.
            if percent < last_progress + 5 and processed != total:
                return
            last_progress = percent
            detail = f"PROSAIL 已反演 {processed:,} / {total:,} 个有效像元"
            lais.update(child.analysis_id, progress_percent=percent, detail=detail,
                        progress_data={"processed_pixels": processed, "total_pixels": total})
            workflows.update_step(workflow_id, "lai", owner_id=owner_id,
                                  status="running", progress_percent=percent, detail=detail)

        observation, report_artifacts = run_lai_html_report(
            image_path=str(reflectance), artifact_output_dir=str(root / "lai"),
            progress_callback=inversion_progress,
            scene_constraints=constraints,
            **({"strict_scene_constraints": True} if workflow.professional_mode else {}),
        )
        if observation.status != "success":
            raise RuntimeError(observation.summary)
        payload = dict(observation.payload or {})
        for key in ("report_path", "lai_raster_path", "lai_preview_path"):
            if not isinstance(payload.get(key), str) or not Path(payload[key]).is_file():
                raise RuntimeError(f"Missing LAI artifact: {key}")
        artifact_ids: dict[str, str] = {}
        for artifact in report_artifacts:
            artifact_ids[artifact.artifact_type] = artifacts.register(child.analysis_id, artifact)
        required = ("lai_html_report", "lai_raster", "lai_preview")
        if any(kind not in artifact_ids for kind in required):
            raise RuntimeError("Incomplete LAI artifact set")
        result = make_lai_result(
            payload, report_artifact_id=artifact_ids["lai_html_report"],
            raster_artifact_id=artifact_ids["lai_raster"],
            preview_artifact_id=artifact_ids["lai_preview"],
        )
        result["observation_at"] = workflow.imagery_snapshot.acquired_at
        result["scene_parameters"] = scene_data
        result["parameters_confirmed"] = workflow.professional_mode
        result["quality"] = assess_lai_raster_quality(
            Path(payload["lai_raster_path"]), workflow.aoi.geometry.model_dump(mode="json"),
        )
        result["imagery_provenance"] = _provenance(workflow)
        result["shared_imagery_workflow_id"] = workflow_id
        result["report_kind"] = "lai_html_report"
        result["report_version"] = REPORT_VERSION
        result.update(register_result_json(
            artifacts, run_id=workflow_id, output_dir=root / "lai",
            title="LAI 反演报告", result=result,
        ))
        lais.update_and_push_event(
            child.analysis_id,
            {"kind": "result", "stage": "completed", "detail": "LAI 反演已完成", "data": result},
            status="completed", stage="completed", progress_percent=100,
            detail="LAI 反演已完成", result=result,
            artifact_ids=list(artifact_ids.values()), completed_at=_now(),
        )
        workflows.update_step(workflow_id, "lai", owner_id=owner_id,
                              status="completed", progress_percent=100,
                              detail="LAI 反演已完成", result=result)
    except Exception:
        logger.exception("analysis_workflow_lai_failed | workflow_id=%s", workflow_id)
        detail = "LAI 反演失败，请检查选区和影像后重试。"
        lais.update_and_push_event(
            child.analysis_id,
            {"kind": "error", "stage": "failed", "detail": detail, "data": {}},
            status="failed", stage="failed", detail=detail,
            result={"error": detail, "scene_parameters": scene_data}, completed_at=_now(),
        )
        workflows.update_step(workflow_id, "lai", owner_id=owner_id,
                              status="failed", detail=detail, result={"error": detail, "scene_parameters": scene_data})
    finally:
        lais.close(child.analysis_id)


def _finish(
    workflows: AnalysisWorkflowStore, workflow_id: str, owner_id: str,
    *, artifact_root: Path | None = None, artifacts: ArtifactStore | None = None,
) -> None:
    workflow = workflows.get(workflow_id, owner_id=owner_id)
    if workflow is None:
        return
    lai_step = next((step for step in workflow.steps if step.step_id == "lai"), None)
    if lai_step and lai_step.status == "completed":
        stored_quality = lai_step.result.get("quality") or {}
        raster_path = lai_step.result.get("lai_raster_path")
        if stored_quality.get("quality_basis") != "aoi_pixels" and isinstance(raster_path, str) and Path(raster_path).is_file():
            try:
                corrected = assess_lai_raster_quality(
                    Path(raster_path), workflow.aoi.geometry.model_dump(mode="json"),
                )
            except Exception:
                logger.exception("analysis_workflow_lai_quality_recheck_failed | workflow_id=%s", workflow_id)
            else:
                workflows.update_step(workflow_id, "lai", owner_id=owner_id,
                                      result={**lai_step.result, "quality": corrected})
                workflow = workflows.get(workflow_id, owner_id=owner_id)
                assert workflow is not None
    statuses = {step.step_id: step.status for step in workflow.steps}
    if "growth" in statuses:
        lai_step = next(step for step in workflow.steps if step.step_id == "lai")
        if lai_step.status == "completed":
            summary = {
                "lai_mean": lai_step.result.get("lai_mean"),
                "vegetation_ratio": lai_step.result.get("vegetation_ratio"),
                "observation_at": lai_step.result.get("observation_at"),
                "quality": lai_step.result.get("quality"),
                "method": "observed_lai_and_vegetation_ratio_summary",
                "warning": "仅汇总当前影像的 LAI 和植被覆盖指标；尚未按作物生育期判定长势等级。",
            }
            if artifacts is not None and artifact_root is not None:
                summary.update(register_growth_report(
                    artifacts, workflow_id=workflow_id,
                    output_dir=artifact_root / "workflows" / workflow_id / "growth",
                    imagery_item_id=workflow.imagery_item_id,
                    observed_at=str(summary["observation_at"] or ""),
                    area_hectares=workflow.aoi.area_hectares, result=summary,
                ))
            workflows.update_step(workflow_id, "growth", owner_id=owner_id,
                                  status="completed", progress_percent=100,
                                  detail="已汇总 LAI 与植被覆盖指标", result=summary)
        else:
            workflows.update_step(workflow_id, "growth", owner_id=owner_id,
                                  status="blocked", detail="LAI 反演未完成，无法汇总长势指标")
    if "potential" in statuses:
        crop_step = next(step for step in workflow.steps if step.step_id == "crop")
        lai_step = next(step for step in workflow.steps if step.step_id == "lai")
        if crop_step.status != "completed" or lai_step.status != "completed":
            workflows.update_step(workflow_id, "potential", owner_id=owner_id,
                                  status="blocked", detail="等待作物识别和 LAI 反演完成")
        elif artifact_root is None or artifacts is None:
            workflows.update_step(workflow_id, "potential", owner_id=owner_id,
                                  status="blocked", detail="冠层指数计算环境尚未准备")
        else:
            workflows.update_step(workflow_id, "potential", owner_id=owner_id,
                                  status="running", progress_percent=20, detail="正在计算 NDVI 与 LAI 冠层指数")
            try:
                result = estimate_yield_potential(
                    workflow, artifact_root / "workflows" / workflow_id / "reflectance.tif",
                )
                report_dir = artifact_root / "workflows" / workflow_id / "potential"
                result.update(register_potential_report(
                    artifacts, workflow_id=workflow_id, output_dir=report_dir,
                    imagery_item_id=workflow.imagery_item_id,
                    observed_at=str(result.get("observed_at") or ""),
                    area_hectares=workflow.aoi.area_hectares, result=result,
                ))
                workflows.update_step(workflow_id, "potential", owner_id=owner_id,
                                      status="completed", progress_percent=100,
                                      detail="单景影像冠层指数已计算；不代表产量吨数", result=result)
            except YieldPotentialError as exc:
                workflows.update_step(workflow_id, "potential", owner_id=owner_id,
                                      status="blocked", detail=str(exc), result={"reason": str(exc)})
            except Exception:
                logger.exception("analysis_workflow_potential_failed | workflow_id=%s", workflow_id)
                workflows.update_step(workflow_id, "potential", owner_id=owner_id,
                                      status="failed", detail="冠层指数计算失败，请重试。")
    if "yield_simple" in statuses:
        simple_step = next(step for step in workflow.steps if step.step_id == "yield_simple")
        if simple_step.status != "completed" or "crop" in run_task_ids:
            def simple_progress(detail: str, percent: int) -> None:
                workflows.update_step(workflow_id, "yield_simple", owner_id=owner_id,
                                      status="running", progress_percent=percent, detail=detail)
            try:
                simple_progress("正在准备自动简化估产", 2)
                result = run_simple_yield(workflow, artifact_root / "simple_yield_cache", simple_progress)
                result.update(register_simple_yield_report(
                    artifacts, workflow_id=workflow_id, output_dir=artifact_root / "workflows" / workflow_id / "yield_simple",
                    imagery_item_id=workflow.imagery_item_id, observed_at=workflow.imagery_snapshot.acquired_at,
                    area_hectares=workflow.aoi.area_hectares, result=result))
                workflows.update_step(workflow_id, "yield_simple", owner_id=owner_id,
                                      status="completed", progress_percent=100,
                                      detail="完整遥感生长期的粮食干重试验估产已完成，尚未本地校准", result=result)
            except SimpleYieldError as exc:
                workflows.update_step(workflow_id, "yield_simple", owner_id=owner_id,
                                      status="blocked", detail=str(exc), result={**exc.details, "reason_code": exc.code, "reason": str(exc), "experimental": True})
            except Exception:
                logger.exception("simple_yield_failed | workflow_id=%s", workflow_id)
                workflows.update_step(workflow_id, "yield_simple", owner_id=owner_id,
                                      status="failed", detail="简化估产数据读取或计算失败，请稍后重试。")
    if "yield" in statuses and workflow.data_mode == "apsim_example":
        example_step = next(step for step in workflow.steps if step.step_id == "yield")
        if example_step.status != "completed" and artifact_root is not None and artifacts is not None:
            try:
                workflows.update_step(workflow_id, "yield", owner_id=owner_id,
                                      status="running", progress_percent=5, detail="正在根据作物识别选择并运行 APSIM 示例")
                output_dir = artifact_root / "workflows" / workflow_id / "yield"
                result = run_example(workflow, output_dir)
                result.update(register_example_report(artifacts, workflow=workflow, result=result, output_dir=output_dir))
                workflows.update_step(workflow_id, "yield", owner_id=owner_id,
                                      status="completed", progress_percent=100, detail=f"{result['crop_label']} APSIM 真实示例模拟已完成；结果不代表当前地块", result=result)
            except ApsimExampleError as exc:
                workflows.update_step(workflow_id, "yield", owner_id=owner_id, status="blocked", detail=str(exc), result={"reason": str(exc)})
            except Exception:
                logger.exception("apsim_example_failed | workflow_id=%s", workflow_id)
                workflows.update_step(workflow_id, "yield", owner_id=owner_id, status="failed", detail="APSIM 示例处理失败，请检查日志后重试。")
    elif "yield" in statuses:
        assessment = assess_yield_inputs(workflow)
        if assessment.status == "ready" and artifact_root is not None and artifacts is not None:
            workflows.update_step(workflow_id, "yield", owner_id=owner_id,
                                  status="running", progress_percent=5, detail="正在运行 APSIM 地块情景")
            try:
                result = run_field_yield(workflow, artifact_root / "workflows" / workflow_id / "yield")
                result["input_assessment"] = assessment.model_dump(mode="json")
                result.update(register_yield_report(
                    artifacts, workflow_id=workflow_id,
                    output_dir=artifact_root / "workflows" / workflow_id / "yield",
                    imagery_item_id=workflow.imagery_item_id,
                    observed_at=workflow.imagery_snapshot.acquired_at,
                    area_hectares=workflow.aoi.area_hectares, result=result,
                ))
                workflows.update_step(workflow_id, "yield", owner_id=owner_id,
                                      status="completed", progress_percent=100,
                                      detail="APSIM 地块情景与同日 LAI 约束已完成", result=result)
            except ApsimFieldError as exc:
                workflows.update_step(workflow_id, "yield", owner_id=owner_id,
                                      status="failed", detail=str(exc),
                                      result={"input_assessment": assessment.model_dump(mode="json"), "error": str(exc)})
            except Exception:
                logger.exception("analysis_workflow_yield_failed | workflow_id=%s", workflow_id)
                workflows.update_step(workflow_id, "yield", owner_id=owner_id,
                                      status="failed", detail="APSIM 运行意外失败，请检查日志或重试。",
                                      result={"input_assessment": assessment.model_dump(mode="json")})
        else:
            detail = f"产量估计尚有 {len(assessment.issues)} 项启动条件未满足"
            workflows.update_step(workflow_id, "yield", owner_id=owner_id,
                                  status="blocked", detail=detail,
                                  result={"input_assessment": assessment.model_dump(mode="json")})
    workflow = workflows.get(workflow_id, owner_id=owner_id)
    if workflow is None:
        return
    statuses = {step.step_id: step.status for step in workflow.steps}
    if any(statuses.get(step) == "failed" for step in ("imagery", "crop", "lai", "potential", "yield_simple", "yield")):
        final_status, final_detail = "failed", "部分任务执行失败；已完成任务的结果已保留"
    elif any(status == "blocked" for status in statuses.values()):
        final_status, final_detail = "blocked", "影像分析已完成，后续任务等待输入或能力接入"
        blocked_simple = next((step for step in workflow.steps if step.step_id == "yield_simple" and step.status == "blocked"), None)
        if blocked_simple is not None and "yield" not in statuses:
            final_detail = blocked_simple.detail
    else:
        final_status, final_detail = "completed", "所选影像分析任务已完成"
    if artifact_root is not None and artifacts is not None:
        _write_workflow_summary_report(workflows, workflow_id, owner_id, artifact_root, artifacts,
                                       status=final_status)
    workflows.update_status(workflow_id, owner_id=owner_id, status=final_status, detail=final_detail)


def _write_workflow_summary_report(
    workflows: AnalysisWorkflowStore, workflow_id: str, owner_id: str,
    artifact_root: Path, artifacts: ArtifactStore, *, status: str | None = None,
) -> None:
    workflow = workflows.get(workflow_id, owner_id=owner_id)
    if workflow is None:
        return
    labels = {"imagery": "影像准备", "crop": "农作物识别", "lai": "PROSAIL/LAI",
              "growth": "长势观测", "potential": "遥感冠层指数", "yield_simple": "自动简化估产（试验）", "yield": "APSIM 估产"}
    sections = []
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
    references = register_map_report(
        artifacts, run_id=workflow_id,
        output_dir=artifact_root / "workflows" / workflow_id / "summary",
        kind="workflow_summary_report", title="估产模拟演示工作流总报告" if workflow.data_mode == "demo" else "地块影像分析工作流总报告",
        context={"工作流 ID": workflow_id, "状态": status or workflow.status,
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
    workflows.set_report(workflow_id, owner_id=owner_id, references=references)


def ensure_workflow_reports(
    workflows: AnalysisWorkflowStore, workflow_id: str, owner_id: str,
    artifact_root: Path, artifacts: ArtifactStore, *, force_summary: bool = False,
) -> None:
    """Make completed historical steps readable without rerunning imagery or models."""
    workflow = workflows.get(workflow_id, owner_id=owner_id)
    if workflow is None or workflow.status not in {"completed", "blocked", "failed"}:
        return
    changed = False
    root = artifact_root / "workflows" / workflow_id
    for step in workflow.steps:
        if step.status != "completed":
            continue
        result = dict(step.result)
        needs_design = result.get("report_version") != REPORT_VERSION
        if workflow.data_mode == "demo":
            if step.step_id in {"yield", "yield_simple"} and (not result.get("report_uri") or needs_design):
                result.update(register_yield_demo_report(artifacts, workflow=workflow, result=result, output_dir=root / step.step_id))
            else:
                continue
        elif step.step_id == "crop" and (not result.get("report_uri") or needs_design):
            result.update(register_crop_report(
                artifacts, run_id=workflow_id, output_dir=root / "crop",
                imagery_item_id=workflow.imagery_item_id,
                observed_at=workflow.imagery_snapshot.acquired_at,
                area_hectares=workflow.aoi.area_hectares, result=result,
            ))
        elif step.step_id == "growth" and (not result.get("report_uri") or needs_design):
            result.update(register_growth_report(
                artifacts, workflow_id=workflow_id, output_dir=root / "growth",
                imagery_item_id=workflow.imagery_item_id,
                observed_at=workflow.imagery_snapshot.acquired_at,
                area_hectares=workflow.aoi.area_hectares, result=result,
            ))
        elif step.step_id == "potential" and (not result.get("report_uri") or needs_design):
            result.update(register_potential_report(
                artifacts, workflow_id=workflow_id, output_dir=root / "potential",
                imagery_item_id=workflow.imagery_item_id,
                observed_at=str(result.get("observed_at") or workflow.imagery_snapshot.acquired_at),
                area_hectares=workflow.aoi.area_hectares, result=result,
            ))
        elif step.step_id == "yield_simple" and (not result.get("report_uri") or needs_design):
            result.update(register_simple_yield_report(
                artifacts, workflow_id=workflow_id, output_dir=root / "yield_simple",
                imagery_item_id=workflow.imagery_item_id, observed_at=workflow.imagery_snapshot.acquired_at,
                area_hectares=workflow.aoi.area_hectares, result=result))
        elif step.step_id == "yield" and workflow.data_mode == "apsim_example" and (not result.get("report_uri") or needs_design):
            result.update(register_example_report(artifacts, workflow=workflow, result=result, output_dir=root / "yield"))
        elif step.step_id == "yield" and (not result.get("report_uri") or needs_design):
            result.update(register_yield_report(
                artifacts, workflow_id=workflow_id, output_dir=root / "yield",
                imagery_item_id=workflow.imagery_item_id,
                observed_at=workflow.imagery_snapshot.acquired_at,
                area_hectares=workflow.aoi.area_hectares, result=result,
            ))
        elif step.step_id == "lai" and result.get("report_uri"):
            result.setdefault("report_kind", "lai_html_report")
            result.setdefault("report_version", REPORT_VERSION)
        if step.step_id == "lai" and result.get("report_uri") and not result.get("report_data_uri"):
            result.update(register_result_json(
                artifacts, run_id=workflow_id, output_dir=root / step.step_id,
                title={"lai": "LAI 反演报告", "potential": "遥感冠层状态试验报告",
                       "yield": "APSIM 地块情景估产报告"}[step.step_id], result=result,
            ))
        if result != step.result:
            workflows.update_step(workflow_id, step.step_id, owner_id=owner_id, result=result)
            changed = True
    if changed or not workflow.report_uri or workflow.report_version != REPORT_VERSION or force_summary:
        _write_workflow_summary_report(workflows, workflow_id, owner_id, artifact_root, artifacts,
                                       status=workflow.status)
