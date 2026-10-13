"""Orchestrate real public observations and the bounded experimental RUE model."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

from infra.imagery.power_weather import fetch_power_weather
from infra.imagery.season_series import read_ndvi_observation, search_season_items
from infra.imagery.stac_provider import SentinelStacProvider
from runtime.simple_yield import SimpleYieldError, estimate_observed_season

CROP_CLASSES = {0: "maize", 3: "spring_wheat", 4: "winter_wheat"}


def resolve_simple_yield_crop(workflow) -> str:
    crop_step = next((step for step in workflow.steps if step.step_id == "crop"), None)
    if crop_step is None or crop_step.status != "completed":
        raise SimpleYieldError("crop_incomplete", "作物识别尚未完成。")
    confirmed = workflow.yield_inputs.confirmed_crop_class_id
    prediction = crop_step.result.get("predicted_class") or {}
    selected = confirmed if confirmed is not None else prediction.get("class_id")
    if selected not in CROP_CLASSES:
        raise SimpleYieldError("crop_confirmation_required", "简化估产首期只支持玉米和小麦，请确认本季地块作物。")
    if confirmed is None:
        scores = sorted((row.get("score", 0) for row in crop_step.result.get("class_scores", [])), reverse=True)
        if len(scores) < 2 or scores[0] < 0.60 or scores[0] - scores[1] < 0.15:
            raise SimpleYieldError("crop_confirmation_required", "当前作物识别不够明确，请选择本季地块作物；无需填写播种或收获日期。")
    return CROP_CLASSES[selected]


def run_simple_yield(workflow, cache_root: Path, progress) -> dict:
    crop = resolve_simple_yield_crop(workflow)
    geometry = workflow.aoi.geometry.model_dump(mode="json")
    end = date.fromisoformat(workflow.imagery_snapshot.acquired_at[:10])
    start = end - timedelta(days=540)
    provider = SentinelStacProvider()
    progress("正在检索近 18 个月的地块影像", 5)
    candidates = search_season_items(provider, geometry, start, end)
    if len(candidates) < 8:
        raise SimpleYieldError("insufficient_observations", "历史影像不足，无法自动识别完整生长季。")
    observations, rejected = [], []
    progress(f"正在读取 {len(candidates)} 景候选影像并检查选区云掩膜", 10)
    # Bound remote reads independently of AOI size and conversation concurrency.
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = {pool.submit(read_ndvi_observation, provider, candidate, geometry, cache_root / "ndvi"): candidate for candidate in candidates}
        for index, future in enumerate(as_completed(pending), 1):
            candidate = pending[future]
            try:
                observations.append(future.result())
            except Exception as exc:
                # A missing/cloudy observation cannot be replaced with synthetic NDVI.
                rejected.append({"date": candidate["date"], "item_id": candidate["item_id"],
                                 "reason": exc.code if isinstance(exc, SimpleYieldError) else "read_unavailable"})
            progress(f"已检查 {index}/{len(candidates)} 景，保留 {len(observations)} 个清晰观测", 10 + int(index / len(candidates) * 60))
    progress("正在获取公开逐日辐射并识别完整生长季", 75)
    weather, provenance = fetch_power_weather(geometry, start, end, cache_root / "weather")
    try:
        result = estimate_observed_season(observations, weather, crop=crop,
                                         as_of=end.isoformat(), area_hectares=workflow.aoi.area_hectares)
    except SimpleYieldError as exc:
        exc.details = {"as_of": end.isoformat(), "crop_type": crop, "observation_count": len(observations),
                       "observations": sorted(observations, key=lambda row: row["date"]),
                       "rejected_observations": rejected, "weather_provenance": provenance}
        raise
    result.update(weather_provenance=provenance, rejected_observations=rejected,
                  imagery_item_id=workflow.imagery_item_id,
                  crop_source="user_confirmed" if workflow.yield_inputs.confirmed_crop_class_id is not None else "image_classifier")
    progress("已计算完整生长季的试验估产，正在生成报告", 95)
    return result
