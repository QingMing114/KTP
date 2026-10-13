"""Isolated KDD2020 purely spatial VGG16 inference process."""

from __future__ import annotations

import json
import os
import sys


def main() -> None:
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
    import numpy as np
    from PIL import Image
    from tensorflow.keras.models import load_model

    model_path, image_path = sys.argv[1:3]
    with Image.open(image_path) as source:
        image = source.convert("RGB").resize((224, 224), Image.Resampling.NEAREST)
        pixels = np.asarray(image, dtype=np.float32)[None, ...] / 255.0
    model = load_model(model_path, compile=False)
    if model.input_shape != (None, 224, 224, 3) or model.output_shape != (None, 6):
        raise ValueError("Unexpected crop model input or output shape")
    scores = np.asarray(model.predict(pixels, verbose=0), dtype=np.float64)
    if scores.shape != (1, 6) or not np.all(np.isfinite(scores)):
        raise ValueError("Invalid crop model output")
    values = scores[0]
    if np.any(values < 0) or np.any(values > 1) or not np.isclose(values.sum(), 1, atol=1e-3):
        raise ValueError("Crop model output is not a six-class softmax vector")
    print(json.dumps({"scores": values.tolist()}, separators=(",", ":")))


if __name__ == "__main__":
    main()
