"""Minimal image loading and preprocessing for the inference service."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, UnidentifiedImageError


def load_image_as_array(image_path: str) -> np.ndarray:
    """Load a local image file into a NumPy array.

    This phase intentionally keeps image loading lightweight with Pillow. Future
    phases can replace this with Rasterio or GDAL to support rich GeoTIFF
    metadata, multi-band stacks, and geospatial transforms.
    """
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"image_path does not exist: {image_path}")
    if not path.is_file():
        raise ValueError(f"image_path is not a file: {image_path}")

    try:
        with Image.open(path) as image:
            if image.mode == "RGBA":
                image = image.convert("RGB")
            array = np.asarray(image, dtype=np.float32)
    except UnidentifiedImageError as exc:
        raise ValueError(f"unsupported image format for path: {image_path}") from exc

    if array.ndim == 2:
        array = array[:, :, np.newaxis]
    if array.ndim != 3:
        raise ValueError(
            f"expected a 2D or 3D image array after loading, received shape={array.shape!r}"
        )
    return array


def validate_image_path(image_path: str) -> str:
    """Validate that the given image path points to a local file."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"image_path does not exist: {image_path}")
    if not path.is_file():
        raise ValueError(f"image_path is not a file: {image_path}")
    return str(path)


def preprocess_image(image_path: str) -> np.ndarray:
    """Apply a minimal normalization placeholder for inference input."""
    image_array = load_image_as_array(validate_image_path(image_path))
    image_array = np.nan_to_num(image_array, nan=0.0, posinf=0.0, neginf=0.0)

    max_value = float(np.max(image_array)) if image_array.size else 0.0
    if max_value > 0.0:
        image_array = image_array / max(max_value, 1.0)
    return image_array.astype(np.float32)
