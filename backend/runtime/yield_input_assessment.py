"""Conservative APSIM input gate for a verified map workflow.

This module never starts APSIM. Server verified weather/soil/management adapters
and same-day LAI comparison are prerequisites for a field yield result.
"""

from __future__ import annotations

import math
import os
from datetime import date

from runtime.apsim_field_dataset import FieldDatasetError, load_field_dataset
from runtime.crop_decision import (
    MIN_SCORE_MARGIN, MIN_TOP_SCORE, needs_score_gate, resolve_crop_class,
)

from schemas.analysis_workflow import AnalysisWorkflowSummary, YieldInputAssessment, YieldInputIssue


CLASS_TO_APSIM = {
    0: "maize", 1: None, 2: "soybean", 3: "wheat", 4: "wheat", 5: None,
}
CLASS_LABELS = ("玉米", "棉花", "大豆", "春小麦", "冬小麦", "大麦")
MIN_LAI_VALID_FRACTION = 0.50
MIN_LAI_VALID_PIXELS = 16


def assess_yield_inputs(workflow: AnalysisWorkflowSummary) -> YieldInputAssessment:
    """Return explicit gaps; arbitrary client references cannot satisfy source checks."""
    steps = {step.step_id: step for step in workflow.steps}
    crop_step, lai_step = steps.get("crop"), steps.get("lai")
    issues: list[YieldInputIssue] = []

    def missing(code: str, field: str, message: str) -> None:
        issues.append(YieldInputIssue(code=code, field=field, message=message))

    predicted = crop_step.result.get("predicted_class", {}) if crop_step and crop_step.status == "completed" else {}
    scores = crop_step.result.get("class_scores", []) if crop_step and crop_step.status == "completed" else []
    score = predicted.get("score") if isinstance(predicted, dict) else None
    score = float(score) if isinstance(score, (int, float)) and math.isfinite(score) else None
    sorted_scores = sorted((float(item["score"]) for item in scores
                            if isinstance(item, dict) and isinstance(item.get("score"), (int, float))
                            and math.isfinite(item["score"])), reverse=True)
    margin = round(sorted_scores[0] - sorted_scores[1], 6) if len(sorted_scores) >= 2 else None
    predicted_id = predicted.get("class_id") if isinstance(predicted, dict) else None
    decided_id, decision = (resolve_crop_class(crop_step.result)
                            if crop_step and crop_step.status == "completed" else (None, None))
    confirmed_id = workflow.yield_inputs.confirmed_crop_class_id
    selected_id = confirmed_id if confirmed_id is not None else decided_id
    decision_source = (decision or {}).get("source")
    if confirmed_id is not None:
        crop_source = "user_confirmed"
    elif decision_source == "llm":
        crop_source = "llm"
    elif decided_id is not None:
        crop_source = "model"
    else:
        crop_source = "unresolved"
    resolved_crop = CLASS_TO_APSIM.get(selected_id) if type(selected_id) is int else None

    if crop_step is None or crop_step.status != "completed":
        missing("crop_analysis_incomplete", "crop", "作物识别尚未完成。")
    elif type(selected_id) is not int or selected_id not in CLASS_TO_APSIM:
        missing("crop_unknown", "crop", "作物类别无法确定，请确认作物。")
    elif resolved_crop is None:
        missing("crop_model_unsupported", "crop", f"{CLASS_LABELS[selected_id]}尚无已验证的 APSIM 地块估产模板。")
    if crop_step and crop_step.status == "completed" and confirmed_id is None and needs_score_gate(decision):
        if score is None or margin is None or score < MIN_TOP_SCORE or margin < MIN_SCORE_MARGIN:
            missing("crop_confirmation_required", "confirmed_crop_class_id",
                    "作物模型分数低于 0.60 或前两类分差低于 0.15，请人工确认地块作物。")

    lai_observation = None
    if lai_step and lai_step.status == "completed":
        result = lai_step.result
        quality = result.get("quality") if isinstance(result.get("quality"), dict) else {}
        lai_observation = {
            "observed_at": result.get("observation_at"), "lai_mean": result.get("lai_mean"),
            "valid_pixel_count": quality.get("valid_pixel_count"),
            "total_pixel_count": quality.get("total_pixel_count"),
            "valid_pixel_fraction": quality.get("valid_pixel_fraction"),
            "raster_artifact_id": result.get("lai_raster_artifact_id"),
            "analysis_id": lai_step.analysis_id,
        }
        lai_mean = lai_observation["lai_mean"]
        valid = lai_observation["valid_pixel_count"]
        fraction = lai_observation["valid_pixel_fraction"]
        if not lai_observation["observed_at"]:
            missing("lai_date_missing", "lai.observed_at", "LAI 缺少影像观测日期。")
        if not isinstance(lai_mean, (int, float)) or not math.isfinite(lai_mean) or lai_mean < 0:
            missing("lai_invalid", "lai.lai_mean", "LAI 观测值无效。")
        if (not isinstance(valid, int) or valid < MIN_LAI_VALID_PIXELS
                or not isinstance(fraction, (int, float)) or fraction < MIN_LAI_VALID_FRACTION):
            missing("lai_quality_low", "lai.quality", "LAI 有效像元需至少 16 个，且覆盖比例至少 50%。")
    else:
        missing("lai_analysis_incomplete", "lai", "PROSAIL/LAI 反演尚未完成。")

    inputs = workflow.yield_inputs
    if inputs.cultivar is None:
        missing("cultivar_missing", "cultivar", "缺少用户确认的品种。")
    if inputs.sowing_date is None:
        missing("sowing_date_missing", "sowing_date", "缺少实际播种日期。")
    elif lai_observation and lai_observation.get("observed_at"):
        try:
            observation_date = date.fromisoformat(str(lai_observation["observed_at"])[:10])
            if inputs.sowing_date > observation_date:
                missing("sowing_after_observation", "sowing_date", "播种日期晚于 LAI 观测日期。")
        except ValueError:
            missing("lai_date_invalid", "lai.observed_at", "LAI 观测日期格式无效。")

    dataset = None
    if workflow.yield_inputs.field_dataset_id:
        try:
            dataset = load_field_dataset(workflow)
            if resolved_crop is not None and dataset["crop_type"] != resolved_crop:
                missing("dataset_crop_mismatch", "field_dataset_id", "数据集作物与识别/确认作物不一致。")
        except FieldDatasetError as exc:
            missing("field_dataset_invalid", "field_dataset_id", str(exc))
    else:
        missing("field_dataset_missing", "field_dataset_id", "缺少已核验的地块 APSIM 数据集。")

    runtime_bin = os.getenv("APSIM_FIELD_MODELS_BIN")
    runtime_ready = bool(runtime_bin and os.getenv("APSIM_FIELD_RUNTIME_VERIFIED") == "1"
                         and os.path.isfile(runtime_bin))
    sources = {
        "aoi": "verified_workflow_aoi",
        "imagery": "verified_sentinel_snapshot",
        "crop": crop_source,
        "lai": "prosail_observation" if lai_observation else "missing",
        "cultivar": "user_supplied" if inputs.cultivar else "missing",
        "sowing_date": "user_supplied" if inputs.sowing_date else "missing",
        "daily_weather": "verified_dataset" if dataset else "unavailable",
        "soil_profile": "verified_dataset" if dataset else "unavailable",
        "management": "verified_dataset" if dataset else "unavailable",
        "apsim_runtime": "verified" if runtime_ready else "unverified",
        "lai_constraint": "implemented" if runtime_ready else "unavailable",
    }
    if not dataset:
        missing("daily_weather_unavailable", "daily_weather", "尚未接入覆盖生长季的真实逐日气象数据及来源。")
        missing("soil_profile_unavailable", "soil_profile", "尚未接入地块土壤剖面及来源。")
        missing("management_unavailable", "management", "尚未接入播种密度、施肥、灌溉等实际管理记录。")
    if not runtime_ready:
        missing("apsim_runtime_unverified", "apsim_runtime", "APSIM 模型运行环境尚未验证或配置。")
        missing("lai_constraint_unavailable", "lai_constraint", "同日 APSIM 模拟 LAI 约束执行环境不可用。")

    return YieldInputAssessment(
        resolved_crop=resolved_crop, crop_source=crop_source,
        crop_model_score=score, crop_score_margin=margin,
        imagery_acquired_at=workflow.imagery_snapshot.acquired_at,
        lai_observation=lai_observation, sources=sources, issues=issues,
        field_dataset=({"dataset_id": dataset["dataset_id"], "verified_by": dataset["verified_by"],
                        "weather_period": dataset["weather_period"],
                        "scenario_ids": [item["id"] for item in dataset["scenarios"]],
                        "source_sha256": {kind: dataset["sources"][kind]["sha256"]
                                          for kind in ("weather", "soil", "management")}} if dataset else None),
        status="ready" if not issues else "blocked",
    )
