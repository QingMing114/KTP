"""Run a bounded diagnostic pass for the real baldness RF pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ml.baldness_rf.diagnostics import diagnose_baldness_rf_run
from shared.logging import configure_logging

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnose the baldness RF model, input crop, features, and outputs.",
    )
    parser.add_argument(
        "--image-path",
        required=True,
        help="Input multispectral GeoTIFF path.",
    )
    parser.add_argument(
        "--model-path",
        required=True,
        help="Random-forest model path.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(BACKEND_ROOT / "var" / "runtime" / "baldness_diagnostics"),
        help="Directory for diagnostics JSON and previews.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging("INFO")
    diagnostics = diagnose_baldness_rf_run(
        input_image_path=args.image_path,
        model_path=args.model_path,
        output_dir=args.output_dir,
    )
    summary = {
        "diagnostics_path": diagnostics.diagnostics_path,
        "input_preview_path": diagnostics.input_image.input_preview_path,
        "class_preview_path": diagnostics.predictions.class_preview_path,
        "confidence_preview_path": diagnostics.predictions.confidence_preview_path,
        "model_classes": diagnostics.model.classes,
        "model_warnings": diagnostics.model.warnings,
        "prediction_warnings": diagnostics.predictions.warnings,
        "dominant_class": diagnostics.predictions.dominant_class,
        "dominant_ratio": diagnostics.predictions.dominant_ratio,
        "non_zero_ratio": diagnostics.predictions.non_zero_ratio,
        "class_distribution": [
            item.model_dump() for item in diagnostics.predictions.class_distribution
        ],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
