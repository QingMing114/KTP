"""Build LAI scene inputs from the selected map observation."""
from __future__ import annotations

from schemas.analysis_workflow import AnalysisWorkflowSummary
from v2.runtime.scene_extractor import extract_scene_parameters


def workspace_lai_query(message, context, recent_runs) -> str:
    """Keep the latest draft's user description only for the current selection."""
    previous = ""
    for run in reversed(recent_runs):
        original = run.input_context.extra_params.get("workspace", {}) if run.input_context else {}
        if (run.status == "completed" and original.get("workspace_id") == context.workspace_id
                and original.get("execution_mode") == context.execution_mode
                and original.get("farm_id") == context.farm_id
                and (original.get("aoi") or {}).get("geometry") == (context.aoi.geometry.model_dump(mode="json") if context.aoi else None)
                and original.get("imagery_item_id") in {None, context.imagery_item_id}
                and any(p.get("type") == "analysis_plan" and "lai" in p.get("data", {}).get("effective_task_ids", [])
                        for p in run.product_parts)):
            previous = run.input_message[:4000]
            break
    return (f"此前当前选区的任务描述：{previous}\n当前请求：{message[:3900]}" if previous else message[:8000])


def configure_workspace_lai(workflow: AnalysisWorkflowSummary, reflectance, llm_provider):
    from shapely.geometry import shape

    geometry = shape(workflow.aoi.geometry.model_dump(mode="json"))
    crop_step = next((s for s in workflow.steps if s.step_id == "crop" and s.status == "completed"), None)
    prediction = crop_step.result.get("predicted_class") if crop_step else None
    crop = (prediction.get("name_zh") or prediction.get("name")) if prediction else None
    scene_context = {
        "acquired_at": workflow.imagery_snapshot.acquired_at,
        "imagery_item_id": workflow.imagery_item_id,
        "aoi_bounds_wgs84": list(geometry.bounds),
        "area_hectares": workflow.aoi.area_hectares,
        "crop_prediction": prediction,
    }
    scene = extract_scene_parameters(
        llm_provider=llm_provider, query=workflow.lai_query or "为当前地图选区配置 LAI 反演参数",
        image_path=str(reflectance), region=None, crop_type=crop,
        scene_context=scene_context,
    )
    return {**scene.model_dump(mode="json"), "context": scene_context}
