"""Feature extraction pipeline migrated from the external baldness RF project."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import threading

import numpy as np
import rasterio
from scipy.ndimage import uniform_filter
from skimage.filters.rank import entropy
from skimage.morphology import square
from skimage.util import img_as_ubyte

logger = logging.getLogger(__name__)

try:
    from skimage.feature import graycomatrix, graycoprops

    _HAS_GLCM = True
except Exception:
    _HAS_GLCM = False


def _ensure_not_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event and cancel_event.is_set():
        raise RuntimeError("task cancelled")


def safe_div(numer: np.ndarray, denom: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    """Safely divide arrays while avoiding zero denominators."""
    output = numer / (denom + eps)
    if numer.shape == denom.shape:
        output = np.clip(output, -1.0, 1.0)
    return output


def local_mean_var(arr: np.ndarray, win: int) -> tuple[np.ndarray, np.ndarray]:
    """Compute fast local mean and variance."""
    mean = uniform_filter(arr, size=win, mode="nearest")
    mean_sq = uniform_filter(arr * arr, size=win, mode="nearest")
    var = np.maximum(0.0, mean_sq - mean * mean)
    return mean, var


def local_entropy(arr: np.ndarray, win: int) -> np.ndarray:
    """Compute local entropy as a lightweight texture proxy."""
    try:
        from skimage.morphology import footprint_rectangle

        footprint = footprint_rectangle((win, win))
    except ImportError:
        footprint = square(win)

    lo, hi = np.nanpercentile(arr, [2, 98])
    if hi <= lo:
        lo, hi = np.nanmin(arr), np.nanmax(arr)
    if hi <= lo:
        quantized = np.zeros_like(arr, dtype=np.uint8)
    else:
        arr_norm = np.clip((arr - lo) / (hi - lo), 0, 1)
        quantized = img_as_ubyte(arr_norm)
    quantized[np.isnan(arr)] = 0
    return entropy(quantized, footprint).astype(np.float32)


def write_stacked(
    path_out: str | Path,
    profile_ref: dict[str, object],
    stack: np.ndarray,
    band_names: list[str],
) -> None:
    """Write a stacked float32 GeoTIFF and companion band-name JSON."""
    output_path = Path(path_out)
    profile = profile_ref.copy()
    profile.update(
        {
            "count": stack.shape[0],
            "dtype": "float32",
            "compress": "deflate",
            "predictor": 3,
            "zlevel": 6,
            "BIGTIFF": "IF_SAFER",
            "nodata": np.nan,
        }
    )
    with rasterio.open(output_path, "w", **profile) as dst:
        for index in range(stack.shape[0]):
            dst.write(stack[index].astype(np.float32), index + 1)
        dst.update_tags(**{f"band_{index + 1}": name for index, name in enumerate(band_names)})
        dst.update_tags(FEATURE_BANDS=json.dumps(band_names, ensure_ascii=False))

    sidecar_path = output_path.with_name(f"{output_path.stem}_bands.json")
    sidecar_path.write_text(
        json.dumps({"bands": band_names}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def extract_features(
    path_in: str | Path,
    path_out: str | Path,
    *,
    win_size: int = 5,
    enable_glcm: bool = False,
    cancel_event: threading.Event | None = None,
) -> str:
    """Extract RF-ready features from a 6-band multispectral GeoTIFF."""
    input_path = str(path_in)
    output_path = str(path_out)
    logger.info("baldness_rf_feature_extraction_started | input=%s", input_path)
    _ensure_not_cancelled(cancel_event)

    with rasterio.open(input_path) as src:
        profile_ref = src.profile
        nodata = src.nodata
        if src.count < 6:
            raise ValueError(f"expected at least 6 bands, found {src.count}")

        band_blue = src.read(1).astype(np.float32)
        band_green = src.read(2).astype(np.float32)
        band_red = src.read(3).astype(np.float32)
        band_re720 = src.read(4).astype(np.float32)
        band_re750 = src.read(5).astype(np.float32)
        band_nir = src.read(6).astype(np.float32)

    _ensure_not_cancelled(cancel_event)

    if nodata is not None:
        valid = (
            (band_blue != nodata)
            & (band_green != nodata)
            & (band_red != nodata)
            & (band_re720 != nodata)
            & (band_re750 != nodata)
            & (band_nir != nodata)
        )
    else:
        valid = (
            (band_blue > 0)
            & (band_green > 0)
            & (band_red > 0)
            & (band_re720 > 0)
            & (band_re750 > 0)
            & (band_nir > 0)
        )
        valid &= np.isfinite(
            band_blue + band_green + band_red + band_re720 + band_re750 + band_nir
        )

    for band in [
        band_blue,
        band_green,
        band_red,
        band_re720,
        band_re750,
        band_nir,
    ]:
        band[~valid] = np.nan

    features: dict[str, np.ndarray] = {
        "B450": band_blue,
        "G555": band_green,
        "R660": band_red,
        "RE720": band_re720,
        "RE750": band_re750,
        "NIR840": band_nir,
    }

    ndvi = safe_div(band_nir - band_red, band_nir + band_red)
    gndvi = safe_div(band_nir - band_green, band_nir + band_green)
    evi2 = 2.5 * (band_nir - band_red) / (band_nir + 2.4 * band_red + 1.0 + 1e-6)
    ndre720 = safe_div(band_nir - band_re720, band_nir + band_re720)
    ndre750 = safe_div(band_nir - band_re750, band_nir + band_re750)
    s_re = (band_re750 - band_re720) / 30.0
    ci_rededge = (band_nir / (band_re750 + 1e-6)) - 1.0
    features.update(
        {
            "NDVI": ndvi,
            "GNDVI": gndvi,
            "EVI2": evi2,
            "NDRE720": ndre720,
            "NDRE750": ndre750,
            "S_RE": s_re,
            "CIrededge": ci_rededge,
        }
    )

    ndwi_green = safe_div(band_green - band_nir, band_green + band_nir)
    nd_blue_nir = safe_div(band_blue - band_nir, band_blue + band_nir)
    features.update({"NDWI_green": ndwi_green, "NDBlueNIR": nd_blue_nir})

    brightness = (band_blue + band_green + band_red) / 3.0
    red_index = (band_red * band_red) / np.maximum(1e-6, band_blue * band_green)
    ndsi_vis = safe_div(band_red - band_green, band_red + band_green)
    features.update(
        {"Brightness": brightness, "RI": red_index, "NDSI_vis": ndsi_vis}
    )

    for feature_name, feature_base in [("NDVI", ndvi), ("NIR840", band_nir)]:
        feature_base = np.nan_to_num(feature_base, nan=0.0)
        mean_value, variance_value = local_mean_var(feature_base, win_size)
        entropy_value = local_entropy(feature_base, win_size)
        features[f"{feature_name}_mean_w{win_size}"] = mean_value
        features[f"{feature_name}_var_w{win_size}"] = variance_value
        features[f"{feature_name}_entropy_w{win_size}"] = entropy_value

    if enable_glcm and _HAS_GLCM:
        logger.info("baldness_rf_feature_extraction_glcm_requested_but_skipped")

    _ensure_not_cancelled(cancel_event)
    band_names = list(features.keys())
    stack = np.stack([features[name] for name in band_names], axis=0)
    stack[np.isnan(stack)] = np.nan
    _ensure_not_cancelled(cancel_event)
    write_stacked(output_path, profile_ref, stack, band_names)
    logger.info("baldness_rf_feature_extraction_succeeded | output=%s", output_path)
    return output_path
