"""Run the KDD2020 spatial crop classifier on a selected Sentinel AOI."""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import numpy as np
import rasterio
from PIL import Image

from infra.imagery.aoi_band_reader import read_prosail_reflectance_aoi

MODEL_NAME = "kdd2020_spatial_vgg16_rgb224_6class_0b9f40f6.h5"
MODEL_SHA256 = "0b9f40f6a0e789d8b383a7b842ba89733ebe8f61db9e6255c18fcf4642667ce5"
CLASS_NAMES = ("Corn", "Cotton", "Soy", "Spring Wheat", "Winter Wheat", "Barley")
CLASS_NAMES_ZH = ("玉米", "棉花", "大豆", "春小麦", "冬小麦", "大麦")


class CropInferenceError(RuntimeError):
    """Expected, user-displayable crop inference failure."""


def _model_path() -> Path:
    default = Path(__file__).resolve().parents[4] / "models" / MODEL_NAME
    return Path(os.getenv("CROP_CLASSIFIER_MODEL_PATH", str(default))).resolve()


def _runner_python() -> str:
    configured = os.getenv("CROP_CLASSIFIER_PYTHON")
    if configured:
        return configured
    dedicated = Path(sys.executable).parent.parent.parent / "ktp-crop-infer" / "bin" / "python"
    return str(dedicated) if dedicated.is_file() else sys.executable


def verify_crop_model() -> Path:
    path = _model_path()
    if not path.is_file():
        raise CropInferenceError("作物识别权重尚未部署，请联系管理员。")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != MODEL_SHA256:
        raise CropInferenceError("作物识别权重校验失败，请联系管理员。")
    return path


def _make_rgb(reflectance_path: Path, output_path: Path) -> dict[str, Any]:
    with rasterio.open(reflectance_path) as dataset:
        # The shared AOI reader writes B02, B03, B04, B07, B08 in this order.
        rgb = dataset.read([3, 2, 1]).astype(np.float32)
        mask = dataset.dataset_mask() > 0
    valid = mask & np.all(np.isfinite(rgb), axis=0) & np.all(rgb > 0, axis=0)
    count = int(valid.sum())
    if count < 16:
        raise CropInferenceError("选区内有效影像像元不足，无法进行作物识别。")
    stretched = np.zeros_like(rgb, dtype=np.uint8)
    ranges = []
    for index in range(3):
        low, high = np.percentile(rgb[index][valid], [2, 98])
        if high <= low:
            high = low + 0.01
        stretched[index][valid] = np.clip((rgb[index][valid] - low) * 255 / (high - low), 0, 255).astype(np.uint8)
        ranges.append([float(low), float(high)])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.moveaxis(stretched, 0, -1), "RGB").save(output_path, quality=95)
    return {"valid_pixels": count, "width": int(rgb.shape[2]), "height": int(rgb.shape[1]), "stretch_p2_p98": ranges}


def run_crop_spatial_analysis(*, item: Any | None = None, geometry: dict | None = None, output_dir: Path,
                              reflectance_path: Path | None = None,
                              progress_callback: Callable[[str, int], None] | None = None) -> dict[str, Any]:
    model_path = verify_crop_model()
    runner = Path(__file__).with_name("crop_spatial_runner.py")
    python = _runner_python()
    if not Path(python).is_file() or not runner.is_file():
        raise CropInferenceError("作物识别运行环境尚未部署，请联系管理员。")
    output_dir.mkdir(parents=True, exist_ok=True)
    if reflectance_path is None:
        if item is None or geometry is None:
            raise CropInferenceError("作物识别缺少已选影像或分析区域。")
        reflectance = read_prosail_reflectance_aoi(
            item=item, geometry=geometry, output_path=output_dir / "reflectance.tif",
            target_resolution_m=20, progress_callback=progress_callback,
        )
    else:
        reflectance = Path(reflectance_path)
        if not reflectance.is_file():
            raise CropInferenceError("共享反射率影像不可用，请重新准备影像。")
    if progress_callback:
        progress_callback("正在准备 RGB 模型输入", 85)
    image_path = output_dir / "rgb_input.jpg"
    image_info = _make_rgb(Path(reflectance), image_path)
    if progress_callback:
        progress_callback("正在执行 KDD2020 作物模型推理", 90)
    try:
        completed = subprocess.run(
            [python, str(runner), str(model_path), str(image_path)],
            capture_output=True, text=True, timeout=300, check=False,
            env={**os.environ, "CUDA_VISIBLE_DEVICES": "-1", "TF_CPP_MIN_LOG_LEVEL": "3"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CropInferenceError("作物模型运行超时或无法启动，请稍后重试。") from exc
    if completed.returncode != 0:
        raise CropInferenceError("作物模型推理失败，请联系管理员检查运行环境。")
    try:
        scores = json.loads(completed.stdout.strip().splitlines()[-1])["scores"]
        if len(scores) != 6 or any(not isinstance(v, (float, int)) or not math.isfinite(v) or v < 0 or v > 1 for v in scores):
            raise ValueError("invalid scores")
        if not math.isclose(sum(scores), 1, abs_tol=1e-3):
            raise ValueError("scores do not sum to one")
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise CropInferenceError("作物模型返回了无效结果，请联系管理员。") from exc
    classes = [
        {"class_id": index, "name": name, "name_zh": CLASS_NAMES_ZH[index], "score": round(float(scores[index]), 6)}
        for index, name in enumerate(CLASS_NAMES)
    ]
    winner = max(classes, key=lambda entry: entry["score"])
    return {
        "predicted_class": winner, "class_scores": classes,
        "input": {"sensor": "Sentinel-2 L2A", "bands": ["B04", "B03", "B02"], "resolution_m": 20,
                  "model_pixels": [224, 224], **image_info},
        "model": {"name": "KDD2020 purely spatial VGG16", "sha256": MODEL_SHA256,
                  "training_source": "https://github.com/kkgadiraju/multi-modal-crop-classification"},
        "warnings": [
            "模型以 NAIP RGB 地块影像训练，当前输入为 Sentinel-2；跨传感器结果未经实地验证。",
            "此结果是整个选区的单一类别预测，分数为模型输出，不能视为校准后的置信度或逐像元分类图。",
        ],
    }
