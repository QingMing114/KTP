"""A single-image canopy indicator, deliberately separate from yield in t/ha.

The index is an exploratory display value. It has no harvest calibration and
must never be returned as an absolute yield estimate.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import rasterio

from runtime.lai_quality import assess_lai_raster_quality
from schemas.analysis_workflow import AnalysisWorkflowSummary


class YieldPotentialError(ValueError):
    pass


def estimate_yield_potential(workflow: AnalysisWorkflowSummary, reflectance_path: Path) -> dict[str, Any]:
    steps = {step.step_id: step for step in workflow.steps}
    crop, lai = steps.get("crop"), steps.get("lai")
    if crop is None or lai is None or crop.status != "completed" or lai.status != "completed":
        raise YieldPotentialError("需要先完成同一景影像的作物识别和 LAI 反演")
    quality = lai.result.get("quality") or {}
    lai_raster_path = lai.result.get("lai_raster_path")
    if isinstance(lai_raster_path, str) and Path(lai_raster_path).is_file():
        quality = assess_lai_raster_quality(
            Path(lai_raster_path), workflow.aoi.geometry.model_dump(mode="json"),
        )
    valid_lai = quality.get("valid_pixel_count")
    fraction = quality.get("valid_pixel_fraction")
    lai_mean = lai.result.get("lai_mean")
    if (not isinstance(valid_lai, int) or valid_lai < 16
            or not isinstance(fraction, (int, float)) or fraction < 0.5):
        raise YieldPotentialError("LAI 有效像元需至少 16 个，且覆盖选区至少 50%")
    if (not isinstance(lai_mean, (int, float)) or not math.isfinite(lai_mean)
            or lai_mean < 0 or lai_mean > 15):
        raise YieldPotentialError("LAI 均值无效或超出模型输入范围")
    observed_at = lai.result.get("observation_at")
    if not isinstance(observed_at, str) or observed_at[:10] != workflow.imagery_snapshot.acquired_at[:10]:
        raise YieldPotentialError("LAI 观测日期与所选影像不一致")
    if not reflectance_path.is_file():
        raise YieldPotentialError("共享 Sentinel 影像已不存在，请重试影像准备")

    with rasterio.open(reflectance_path) as source:
        if source.count < 5:
            raise YieldPotentialError("共享影像缺少计算 NDVI 所需的红光或近红外波段")
        red = source.read(3, masked=True).filled(np.nan)
        nir = source.read(5, masked=True).filled(np.nan)
    valid = (np.isfinite(red) & np.isfinite(nir) & (red > 0) & (nir > 0)
             & ((red + nir) > 0))
    if int(np.count_nonzero(valid)) < 16:
        raise YieldPotentialError("NDVI 有效像元不足 16 个，无法评估冠层状态")
    ndvi_values = (nir[valid] - red[valid]) / (nir[valid] + red[valid])
    ndvi_values = ndvi_values[np.isfinite(ndvi_values) & (ndvi_values >= -1) & (ndvi_values <= 1)]
    if len(ndvi_values) < 16:
        raise YieldPotentialError("NDVI 有效像元不足 16 个，无法评估冠层状态")
    ndvi_median = float(np.median(ndvi_values))

    # Fixed, transparent screening formula; these constants are not fitted
    # to harvest data and cannot turn a single image into grain yield.
    lai_component = 1.0 - math.exp(-0.5 * float(lai_mean))
    ndvi_component = min(1.0, max(0.0, (ndvi_median - 0.2) / 0.6))
    index = round(100.0 * math.sqrt(lai_component * ndvi_component), 1)
    signal_warning = ("当前 NDVI 低于 0.2，可能是裸地、收获后地块或非作物区域；指数为 0 不代表实际产量为 0。"
                      if ndvi_median < 0.2 else None)
    prediction = crop.result.get("predicted_class") or {}
    return {
        "method": "single_image_canopy_index_v1",
        "output_type": "uncalibrated_canopy_index",
        "canopy_index": index,
        "lai_component": round(lai_component, 4),
        "ndvi_component": round(ndvi_component, 4),
        "ndvi_median": round(ndvi_median, 4),
        "ndvi_valid_pixels": len(ndvi_values),
        "lai_mean": round(float(lai_mean), 3),
        "lai_valid_fraction": fraction,
        "lai_valid_pixels": valid_lai,
        "observed_at": observed_at,
        "crop_prediction": prediction,
        "imagery_item_id": workflow.imagery_item_id,
        "lai_analysis_id": lai.analysis_id,
        "crop_analysis_id": crop.analysis_id,
        "signal_warning": signal_warning,
        "uncertainty_note": "仅表示该景影像的冠层状态；未用实收产量校准，不能解释为产量、产量百分比或跨地块排名。",
    }
