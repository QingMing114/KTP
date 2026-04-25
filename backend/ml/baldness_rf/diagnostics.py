"""Diagnostics helpers for inspecting baldness RF inputs, features, and outputs."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import joblib
import numpy as np
import rasterio
from PIL import Image
from pydantic import Field

from ml.baldness_rf.classifier import run_rf_inference
from ml.baldness_rf.feature_extractor import extract_features
from shared.schemas.common import BaseSchema

logger = logging.getLogger(__name__)

_CLASS_PALETTE: dict[int, tuple[int, int, int]] = {
    0: (0, 0, 0),
    1: (55, 126, 184),
    2: (77, 175, 74),
    3: (255, 127, 0),
    4: (228, 26, 28),
    5: (152, 78, 163),
    6: (166, 86, 40),
    7: (247, 129, 191),
    8: (153, 153, 153),
}


class ArrayStats(BaseSchema):
    """Basic numeric summary for one band or one raster."""

    min: float = Field(..., description="Minimum finite value.")
    max: float = Field(..., description="Maximum finite value.")
    mean: float = Field(..., description="Mean finite value.")
    std: float = Field(..., description="Standard deviation of finite values.")
    p01: float = Field(..., description="1st percentile.")
    p50: float = Field(..., description="Median.")
    p99: float = Field(..., description="99th percentile.")
    valid_ratio: float = Field(..., description="Finite-value ratio.")


class BandDiagnostic(BaseSchema):
    """Summary for one source band or one extracted feature band."""

    name: str = Field(..., description="Band or feature name.")
    stats: ArrayStats = Field(..., description="Numeric summary.")


class ModelFeatureImportance(BaseSchema):
    """Named feature importance from the RF model."""

    rank: int = Field(..., description="Descending importance rank.")
    feature_name: str = Field(..., description="Feature name or placeholder label.")
    importance: float = Field(..., description="Feature importance value.")


class ModelDiagnostics(BaseSchema):
    """RF model structure summary."""

    model_type: str = Field(..., description="Loaded model class name.")
    classes: list[int] = Field(default_factory=list, description="Model class labels.")
    n_features_in: int = Field(..., description="Expected input feature count.")
    n_estimators: int = Field(..., description="Number of trees in the forest.")
    feature_importances_top: list[ModelFeatureImportance] = Field(
        default_factory=list,
        description="Top named feature importances.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Warnings about model semantics or compatibility.",
    )


class InputImageDiagnostics(BaseSchema):
    """Summary of the raw multispectral input image."""

    image_path: str = Field(..., description="Input image path.")
    width: int = Field(..., description="Image width.")
    height: int = Field(..., description="Image height.")
    band_count: int = Field(..., description="Band count.")
    input_preview_path: str = Field(..., description="Rendered RGB preview path.")
    bands: list[BandDiagnostic] = Field(
        default_factory=list,
        description="Per-band descriptive statistics.",
    )


class FeatureDiagnostics(BaseSchema):
    """Summary of the extracted feature stack."""

    feature_path: str = Field(..., description="Feature stack path.")
    feature_count: int = Field(..., description="Number of extracted features.")
    features: list[BandDiagnostic] = Field(
        default_factory=list,
        description="Per-feature descriptive statistics.",
    )


class ClassDistributionItem(BaseSchema):
    """Distribution summary for one predicted class."""

    class_value: int = Field(..., description="Predicted class value.")
    count: int = Field(..., description="Pixel count for this class.")
    ratio: float = Field(..., description="Pixel ratio for this class.")
    mean_confidence: float = Field(..., description="Mean max-probability for this class.")
    mask_preview_path: str | None = Field(
        default=None,
        description="Optional binary preview for this class only.",
    )


class PredictionDiagnostics(BaseSchema):
    """Summary of the predicted class/confidence rasters."""

    class_map_path: str = Field(..., description="Classification raster path.")
    confidence_map_path: str = Field(..., description="Confidence raster path.")
    class_preview_path: str = Field(..., description="Colorized class-map preview path.")
    confidence_preview_path: str = Field(
        ...,
        description="Grayscale confidence preview path.",
    )
    confidence_stats: ArrayStats = Field(..., description="Confidence summary stats.")
    class_distribution: list[ClassDistributionItem] = Field(
        default_factory=list,
        description="Per-class distribution and confidence summary.",
    )
    dominant_class: int | None = Field(default=None, description="Most frequent class.")
    dominant_ratio: float = Field(..., description="Most frequent class ratio.")
    non_zero_ratio: float = Field(
        ...,
        description="Fraction of pixels whose class value is non-zero.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Warnings about suspicious output structure.",
    )


class BaldnessRfDiagnostics(BaseSchema):
    """Combined diagnostic payload for one RF inference run."""

    input_image: InputImageDiagnostics = Field(..., description="Input image summary.")
    model: ModelDiagnostics = Field(..., description="Model summary.")
    features: FeatureDiagnostics = Field(..., description="Feature stack summary.")
    predictions: PredictionDiagnostics = Field(..., description="Prediction summary.")
    diagnostics_path: str = Field(..., description="Written JSON diagnostics path.")


def diagnose_baldness_rf_run(
    *,
    input_image_path: str | Path,
    model_path: str | Path,
    output_dir: str | Path,
) -> BaldnessRfDiagnostics:
    """Run RF diagnostics and persist JSON plus preview artifacts."""
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    feature_path = output_root / "features.tif"
    class_map_path = output_root / "class.tif"
    confidence_map_path = output_root / "confidence.tif"
    diagnostics_path = output_root / "diagnostics.json"

    logger.info(
        "baldness_rf_diagnostics_started | image=%s | model=%s | output_dir=%s",
        input_image_path,
        model_path,
        output_root,
    )

    input_image = analyze_input_image(
        image_path=input_image_path,
        output_dir=output_root,
    )
    extract_features(
        input_image_path,
        feature_path,
        win_size=5,
    )
    features = analyze_feature_stack(feature_path=feature_path)
    model = analyze_rf_model(model_path=model_path, feature_names=[f.name for f in features.features])
    run_rf_inference(
        input_feature_path=feature_path,
        model_path=model_path,
        output_class_path=class_map_path,
        output_conf_path=confidence_map_path,
    )
    predictions = analyze_prediction_outputs(
        class_map_path=class_map_path,
        confidence_map_path=confidence_map_path,
        output_dir=output_root,
        model_classes=model.classes,
    )

    diagnostics = BaldnessRfDiagnostics(
        input_image=input_image,
        model=model,
        features=features,
        predictions=predictions,
        diagnostics_path=str(diagnostics_path),
    )
    diagnostics_path.write_text(
        diagnostics.model_dump_json(indent=2),
        encoding="utf-8",
    )
    logger.info(
        "baldness_rf_diagnostics_succeeded | diagnostics=%s | dominant_class=%s | dominant_ratio=%.4f",
        diagnostics_path,
        diagnostics.predictions.dominant_class,
        diagnostics.predictions.dominant_ratio,
    )
    return diagnostics


def analyze_input_image(
    *,
    image_path: str | Path,
    output_dir: str | Path,
) -> InputImageDiagnostics:
    """Summarize the raw multispectral image and render an RGB preview."""
    image_file = Path(image_path)
    output_root = Path(output_dir)
    preview_path = output_root / "input_preview.png"

    with rasterio.open(image_file) as dataset:
        array = dataset.read().astype(np.float32)
        width = dataset.width
        height = dataset.height
        band_count = dataset.count

    _save_rgb_preview(array, preview_path)
    bands = [
        BandDiagnostic(name=f"band_{index + 1}", stats=_array_stats(array[index]))
        for index in range(array.shape[0])
    ]
    return InputImageDiagnostics(
        image_path=str(image_file),
        width=width,
        height=height,
        band_count=band_count,
        input_preview_path=str(preview_path),
        bands=bands,
    )


def analyze_feature_stack(*, feature_path: str | Path) -> FeatureDiagnostics:
    """Summarize the extracted feature stack and recover feature names."""
    feature_file = Path(feature_path)
    sidecar_path = feature_file.with_name(f"{feature_file.stem}_bands.json")
    feature_names = _load_feature_names(sidecar_path)

    with rasterio.open(feature_file) as dataset:
        stack = dataset.read().astype(np.float32)

    if not feature_names:
        feature_names = [f"feature_{index + 1}" for index in range(stack.shape[0])]

    features = [
        BandDiagnostic(
            name=feature_names[index] if index < len(feature_names) else f"feature_{index + 1}",
            stats=_array_stats(stack[index]),
        )
        for index in range(stack.shape[0])
    ]
    return FeatureDiagnostics(
        feature_path=str(feature_file),
        feature_count=stack.shape[0],
        features=features,
    )


def analyze_rf_model(
    *,
    model_path: str | Path,
    feature_names: list[str] | None = None,
) -> ModelDiagnostics:
    """Load the RF model and summarize basic structure plus importances."""
    rf_model = joblib.load(model_path)
    raw_importances = list(getattr(rf_model, "feature_importances_", []))
    resolved_feature_names = feature_names or [
        f"feature_{index + 1}" for index in range(len(raw_importances))
    ]
    top_pairs = sorted(
        enumerate(raw_importances, start=1),
        key=lambda item: float(item[1]),
        reverse=True,
    )[:10]
    feature_importances_top = [
        ModelFeatureImportance(
            rank=rank,
            feature_name=resolved_feature_names[index - 1]
            if index - 1 < len(resolved_feature_names)
            else f"feature_{index}",
            importance=round(float(importance), 6),
        )
        for rank, (index, importance) in enumerate(top_pairs, start=1)
    ]
    classes = [int(item) for item in getattr(rf_model, "classes_", [])]
    warnings: list[str] = []
    if len(classes) > 2 and any(item > 0 for item in classes):
        warnings.append(
            "model is multi-class; treating class values greater than zero as a binary baldness mask is unsafe"
        )
    return ModelDiagnostics(
        model_type=type(rf_model).__name__,
        classes=classes,
        n_features_in=int(getattr(rf_model, "n_features_in_", 0)),
        n_estimators=int(getattr(rf_model, "n_estimators", 0)),
        feature_importances_top=feature_importances_top,
        warnings=warnings,
    )


def analyze_prediction_outputs(
    *,
    class_map_path: str | Path,
    confidence_map_path: str | Path,
    output_dir: str | Path,
    model_classes: list[int] | None = None,
) -> PredictionDiagnostics:
    """Summarize class and confidence outputs and render previews."""
    class_file = Path(class_map_path)
    confidence_file = Path(confidence_map_path)
    output_root = Path(output_dir)
    class_preview_path = output_root / "class_preview.png"
    confidence_preview_path = output_root / "confidence_preview.png"
    class_masks_dir = output_root / "class_masks"
    class_masks_dir.mkdir(parents=True, exist_ok=True)

    with rasterio.open(class_file) as dataset:
        class_map = dataset.read(1)
    with rasterio.open(confidence_file) as dataset:
        confidence_map = dataset.read(1).astype(np.float32)

    _save_class_preview(class_map, class_preview_path)
    _save_grayscale_preview(confidence_map, confidence_preview_path)

    finite_conf = confidence_map[np.isfinite(confidence_map)]
    confidence_stats = _array_stats(finite_conf)
    unique_values, counts = np.unique(class_map, return_counts=True)
    total_pixels = int(class_map.size)
    class_distribution: list[ClassDistributionItem] = []
    warnings: list[str] = []
    dominant_class = None
    dominant_ratio = 0.0

    for class_value, count in zip(unique_values.tolist(), counts.tolist(), strict=False):
        class_mask = class_map == class_value
        ratio = count / total_pixels if total_pixels else 0.0
        mean_confidence = float(np.nanmean(confidence_map[class_mask])) if class_mask.any() else 0.0
        mask_preview_path = class_masks_dir / f"class_{int(class_value)}.png"
        _save_binary_mask_preview(class_mask, mask_preview_path)
        class_distribution.append(
            ClassDistributionItem(
                class_value=int(class_value),
                count=int(count),
                ratio=round(float(ratio), 6),
                mean_confidence=round(float(np.clip(mean_confidence, 0.0, 1.0)), 6),
                mask_preview_path=str(mask_preview_path),
            )
        )
        if ratio > dominant_ratio:
            dominant_ratio = ratio
            dominant_class = int(class_value)

    non_zero_ratio = float(np.count_nonzero(class_map > 0) / total_pixels) if total_pixels else 0.0
    if model_classes and len(model_classes) > 2 and non_zero_ratio >= 0.99:
        warnings.append(
            "nearly all pixels are non-zero, which suggests the current binary summarization rule is collapsing a multi-class output"
        )
    if dominant_class is not None and dominant_ratio >= 0.9:
        warnings.append(
            f"class {dominant_class} dominates {dominant_ratio:.2%} of the image"
        )
    if confidence_stats.mean >= 0.95 and dominant_ratio >= 0.9:
        warnings.append(
            "prediction is both highly confident and highly collapsed, which often indicates input-domain or label-mapping issues"
        )

    return PredictionDiagnostics(
        class_map_path=str(class_file),
        confidence_map_path=str(confidence_file),
        class_preview_path=str(class_preview_path),
        confidence_preview_path=str(confidence_preview_path),
        confidence_stats=confidence_stats,
        class_distribution=class_distribution,
        dominant_class=dominant_class,
        dominant_ratio=round(float(dominant_ratio), 6),
        non_zero_ratio=round(float(non_zero_ratio), 6),
        warnings=warnings,
    )


def _load_feature_names(sidecar_path: Path) -> list[str]:
    if not sidecar_path.exists():
        return []
    payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    names = payload.get("bands", [])
    return [str(item) for item in names]


def _array_stats(array: np.ndarray) -> ArrayStats:
    finite = np.asarray(array, dtype=np.float32)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return ArrayStats(
            min=0.0,
            max=0.0,
            mean=0.0,
            std=0.0,
            p01=0.0,
            p50=0.0,
            p99=0.0,
            valid_ratio=0.0,
        )
    total_count = int(np.asarray(array).size)
    return ArrayStats(
        min=round(float(np.min(finite)), 6),
        max=round(float(np.max(finite)), 6),
        mean=round(float(np.mean(finite)), 6),
        std=round(float(np.std(finite)), 6),
        p01=round(float(np.percentile(finite, 1)), 6),
        p50=round(float(np.percentile(finite, 50)), 6),
        p99=round(float(np.percentile(finite, 99)), 6),
        valid_ratio=round(float(finite.size / total_count), 6) if total_count else 0.0,
    )


def _save_rgb_preview(multiband_array: np.ndarray, output_path: Path) -> None:
    if multiband_array.shape[0] >= 3:
        rgb = np.stack(
            [
                multiband_array[2],
                multiband_array[1],
                multiband_array[0],
            ],
            axis=-1,
        )
    else:
        gray = multiband_array[0]
        rgb = np.stack([gray, gray, gray], axis=-1)
    preview = _normalize_rgb(rgb)
    Image.fromarray(preview).save(output_path)


def _save_class_preview(class_map: np.ndarray, output_path: Path) -> None:
    colored = np.zeros((*class_map.shape, 3), dtype=np.uint8)
    for class_value in np.unique(class_map):
        color = _CLASS_PALETTE.get(int(class_value), (240, 240, 240))
        colored[class_map == class_value] = color
    Image.fromarray(colored).save(output_path)


def _save_grayscale_preview(confidence_map: np.ndarray, output_path: Path) -> None:
    normalized = _normalize_single_band(confidence_map)
    Image.fromarray(normalized).save(output_path)


def _save_binary_mask_preview(mask: np.ndarray, output_path: Path) -> None:
    preview = np.where(mask, 255, 0).astype(np.uint8)
    Image.fromarray(preview).save(output_path)


def _normalize_rgb(rgb: np.ndarray) -> np.ndarray:
    channels: list[np.ndarray] = []
    for channel_index in range(rgb.shape[-1]):
        channels.append(_normalize_single_band(rgb[..., channel_index]))
    return np.stack(channels, axis=-1)


def _normalize_single_band(band: np.ndarray) -> np.ndarray:
    finite = band[np.isfinite(band)]
    if finite.size == 0:
        return np.zeros_like(band, dtype=np.uint8)
    lo = float(np.percentile(finite, 2))
    hi = float(np.percentile(finite, 98))
    if hi <= lo:
        lo = float(np.min(finite))
        hi = float(np.max(finite))
    if hi <= lo:
        return np.zeros_like(band, dtype=np.uint8)
    normalized = np.clip((np.nan_to_num(band, nan=lo) - lo) / (hi - lo), 0.0, 1.0)
    return (normalized * 255).astype(np.uint8)
