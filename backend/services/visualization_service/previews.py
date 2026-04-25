"""Preview helpers for workflow visualization artifacts."""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image

from services.visualization_service.schemas import VisualizationArtifact

_PALETTE: list[tuple[int, int, int]] = [
    (17, 24, 39),
    (214, 122, 62),
    (45, 125, 210),
    (35, 154, 120),
    (224, 87, 109),
    (124, 92, 191),
    (190, 150, 62),
    (89, 168, 201),
    (155, 96, 76),
    (83, 118, 54),
]


def build_class_palette(class_values: list[int]) -> dict[int, tuple[int, int, int]]:
    """Return a stable color palette for one class map."""
    palette = {0: (14, 20, 27)}
    next_index = 1
    for value in sorted({int(item) for item in class_values}):
        if value == 0:
            continue
        palette[value] = _PALETTE[next_index % len(_PALETTE)]
        next_index += 1
    return palette


def color_to_hex(color: tuple[int, int, int]) -> str:
    """Return a CSS hex color string for an RGB tuple."""
    return f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"


def build_artifact_preview(
    *,
    artifact_key: str,
    title: str,
    artifact_kind: str,
    source_uri: str | None,
    output_dir: Path,
) -> tuple[VisualizationArtifact, str | None]:
    """Build one preview image plus an inline data URI when possible."""
    source_path = _resolve_local_path(source_uri)
    if source_path is None:
        artifact = VisualizationArtifact(
            artifact_key=artifact_key,
            title=title,
            artifact_kind=artifact_kind,
            source_uri=source_uri,
            preview_uri=None,
            available=False,
            note="artifact path was not provided",
        )
        return artifact, None

    if not source_path.exists():
        artifact = VisualizationArtifact(
            artifact_key=artifact_key,
            title=title,
            artifact_kind=artifact_kind,
            source_uri=str(source_path),
            preview_uri=None,
            available=False,
            note="artifact is missing on disk",
        )
        return artifact, None

    preview_path = output_dir / f"{artifact_key}.png"
    try:
        if artifact_kind == "input_image":
            _render_input_preview(source_path, preview_path)
        elif artifact_kind == "class_map":
            _render_class_map_preview(source_path, preview_path)
        elif artifact_kind == "mask":
            _render_mask_preview(source_path, preview_path)
        elif artifact_kind == "confidence_map":
            _render_confidence_preview(source_path, preview_path)
        else:
            raise ValueError(f"unsupported artifact kind: {artifact_kind}")
    except Exception as exc:
        artifact = VisualizationArtifact(
            artifact_key=artifact_key,
            title=title,
            artifact_kind=artifact_kind,
            source_uri=str(source_path),
            preview_uri=None,
            available=True,
            note=f"preview generation failed: {exc}",
        )
        return artifact, None

    artifact = VisualizationArtifact(
        artifact_key=artifact_key,
        title=title,
        artifact_kind=artifact_kind,
        source_uri=str(source_path),
        preview_uri=str(preview_path),
        available=True,
        note=None,
    )
    return artifact, _encode_png_as_data_uri(preview_path)


def _resolve_local_path(source_uri: str | None) -> Path | None:
    if source_uri is None or not str(source_uri).strip():
        return None
    resolved = str(source_uri).strip()
    if resolved.startswith("file://"):
        resolved = resolved.removeprefix("file://")
    return Path(resolved).expanduser()


def _render_input_preview(source_path: Path, preview_path: Path) -> None:
    if source_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}:
        try:
            with rasterio.open(source_path) as dataset:
                stack = dataset.read().astype(np.float32)
            rgb = _multiband_to_rgb(stack)
            _save_rgb_array(rgb, preview_path)
            return
        except rasterio.errors.RasterioIOError:
            pass

    with Image.open(source_path) as image:
        image.convert("RGB").save(preview_path)


def _render_class_map_preview(source_path: Path, preview_path: Path) -> None:
    with rasterio.open(source_path) as dataset:
        class_map = dataset.read(1)
    palette = build_class_palette([int(value) for value in np.unique(class_map)])
    rgb = np.zeros((class_map.shape[0], class_map.shape[1], 3), dtype=np.uint8)
    for value, color in palette.items():
        rgb[class_map == value] = color
    _save_rgb_array(rgb, preview_path)


def _render_mask_preview(source_path: Path, preview_path: Path) -> None:
    mask = _read_single_band(source_path)
    canvas = np.zeros((mask.shape[0], mask.shape[1], 3), dtype=np.uint8)
    canvas[mask > 0] = np.array([239, 146, 61], dtype=np.uint8)
    canvas[mask <= 0] = np.array([18, 24, 29], dtype=np.uint8)
    _save_rgb_array(canvas, preview_path)


def _render_confidence_preview(source_path: Path, preview_path: Path) -> None:
    confidence = _read_single_band(source_path).astype(np.float32)
    normalized = _normalize_scalar(confidence)
    rgb = _apply_gradient(normalized)
    _save_rgb_array(rgb, preview_path)


def _read_single_band(source_path: Path) -> np.ndarray:
    try:
        with rasterio.open(source_path) as dataset:
            return dataset.read(1)
    except rasterio.errors.RasterioIOError:
        with Image.open(source_path) as image:
            return np.asarray(image)


def _multiband_to_rgb(stack: np.ndarray) -> np.ndarray:
    if stack.ndim == 2:
        stack = np.repeat(stack[np.newaxis, ...], 3, axis=0)
    if stack.ndim != 3:
        raise ValueError(f"unsupported raster dimensions: {stack.shape}")
    if stack.shape[0] >= 3:
        rgb_stack = stack[:3]
    else:
        rgb_stack = np.repeat(stack[:1], 3, axis=0)
    channels = [_normalize_band(channel) for channel in rgb_stack]
    return np.stack(channels, axis=-1)


def _normalize_band(band: np.ndarray) -> np.ndarray:
    finite = band[np.isfinite(band)]
    if finite.size == 0:
        return np.zeros_like(band, dtype=np.uint8)
    low = float(np.percentile(finite, 2))
    high = float(np.percentile(finite, 98))
    if high <= low:
        high = low + 1.0
    normalized = np.clip((band - low) / (high - low), 0.0, 1.0)
    return np.nan_to_num(normalized * 255.0, nan=0.0).astype(np.uint8)


def _normalize_scalar(array: np.ndarray) -> np.ndarray:
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return np.zeros_like(array, dtype=np.float32)
    low = float(np.min(finite))
    high = float(np.max(finite))
    if low >= 0.0 and high <= 1.0:
        normalized = np.clip(array, 0.0, 1.0)
    else:
        if high <= low:
            high = low + 1.0
        normalized = np.clip((array - low) / (high - low), 0.0, 1.0)
    return np.nan_to_num(normalized, nan=0.0).astype(np.float32)


def _apply_gradient(normalized: np.ndarray) -> np.ndarray:
    low = np.array([23, 34, 59], dtype=np.float32)
    mid = np.array([76, 145, 149], dtype=np.float32)
    high = np.array([240, 194, 112], dtype=np.float32)
    normalized = np.clip(normalized, 0.0, 1.0)
    lower_weight = np.clip(normalized / 0.5, 0.0, 1.0)[..., np.newaxis]
    upper_weight = np.clip((normalized - 0.5) / 0.5, 0.0, 1.0)[..., np.newaxis]
    lower_blend = (1.0 - lower_weight) * low + lower_weight * mid
    upper_blend = (1.0 - upper_weight) * mid + upper_weight * high
    blended = np.where(normalized[..., np.newaxis] < 0.5, lower_blend, upper_blend)
    return blended.astype(np.uint8)


def _save_rgb_array(rgb: np.ndarray, preview_path: Path) -> None:
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))
    image.save(preview_path)


def _encode_png_as_data_uri(preview_path: Path) -> str:
    with Image.open(preview_path) as image:
        buffer = BytesIO()
        image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"
