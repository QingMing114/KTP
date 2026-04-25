"""Random-forest classification pipeline migrated from the external baldness project."""

from __future__ import annotations

import logging
from pathlib import Path
import threading

import joblib
import numpy as np
import rasterio
from rasterio.windows import Window
from tqdm import tqdm

logger = logging.getLogger(__name__)

TILE_SIZE = 1024
EPSILON = 0.0


def _ensure_not_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event and cancel_event.is_set():
        raise RuntimeError("task cancelled")


def run_rf_inference(
    *,
    input_feature_path: str | Path,
    model_path: str | Path,
    output_class_path: str | Path,
    output_conf_path: str | Path,
    cancel_event: threading.Event | None = None,
) -> tuple[str, str]:
    """Run tiled RF inference over the extracted feature GeoTIFF."""
    feature_path = str(input_feature_path)
    model_file = str(model_path)
    class_path = str(output_class_path)
    conf_path = str(output_conf_path)
    logger.info(
        "baldness_rf_classifier_started | features=%s | model=%s",
        feature_path,
        model_file,
    )
    if not Path(model_file).exists():
        raise FileNotFoundError(f"model file not found: {model_file}")

    rf_model = joblib.load(model_file)
    with rasterio.open(feature_path) as src:
        profile = src.profile
        height = src.height
        width = src.width
        class_profile = profile.copy()
        class_profile.update({"count": 1, "dtype": rasterio.uint16, "nodata": 0})
        conf_profile = profile.copy()
        conf_profile.update({"count": 1, "dtype": rasterio.float32, "nodata": np.nan})

    Path(class_path).parent.mkdir(parents=True, exist_ok=True)
    Path(conf_path).parent.mkdir(parents=True, exist_ok=True)

    with (
        rasterio.open(feature_path) as src,
        rasterio.open(class_path, "w", **class_profile) as dst_class,
        rasterio.open(conf_path, "w", **conf_profile) as dst_conf,
    ):
        for row_offset in tqdm(
            range(0, height, TILE_SIZE),
            desc="[baldness_rf] inference",
            leave=False,
        ):
            _ensure_not_cancelled(cancel_event)
            num_rows = min(TILE_SIZE, height - row_offset)
            for col_offset in range(0, width, TILE_SIZE):
                _ensure_not_cancelled(cancel_event)
                num_cols = min(TILE_SIZE, width - col_offset)
                window = Window(col_offset, row_offset, num_cols, num_rows)
                tile = src.read(window=window)
                tile = np.transpose(tile, (1, 2, 0))

                valid_2d = np.any(np.abs(tile) > EPSILON, axis=2)
                flattened = tile.reshape(-1, tile.shape[2])
                flattened_num = np.nan_to_num(flattened, nan=0.0)
                valid_flat = valid_2d.reshape(-1)

                predicted_class = np.zeros(flattened.shape[0], dtype=np.uint16)
                predicted_conf = np.full(flattened.shape[0], np.nan, dtype=np.float32)
                if valid_flat.any():
                    probabilities = rf_model.predict_proba(flattened_num[valid_flat])
                    predicted_class[valid_flat] = rf_model.classes_[
                        np.argmax(probabilities, axis=1)
                    ].astype(np.uint16)
                    predicted_conf[valid_flat] = np.max(probabilities, axis=1).astype(
                        np.float32
                    )

                dst_class.write(predicted_class.reshape(num_rows, num_cols), 1, window=window)
                dst_conf.write(predicted_conf.reshape(num_rows, num_cols), 1, window=window)
                mask_tile = valid_2d.astype("uint8") * 255
                dst_class.write_mask(mask_tile, window=window)
                dst_conf.write_mask(mask_tile, window=window)

    logger.info(
        "baldness_rf_classifier_succeeded | class_path=%s | conf_path=%s",
        class_path,
        conf_path,
    )
    return class_path, conf_path
