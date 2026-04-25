"""Tests for the workflow visualization service."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from services.visualization_service.client import LocalVisualizationServiceClient
from services.visualization_service.config import VisualizationServiceConfig


def _write_multiband_raster(path: Path) -> str:
    data = np.stack(
        [
            np.full((24, 24), fill_value=value, dtype=np.float32)
            for value in (45, 90, 135)
        ],
        axis=0,
    )
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=24,
        width=24,
        count=3,
        dtype="float32",
        transform=from_origin(100, 100, 1, 1),
    ) as dataset:
        dataset.write(data)
    return str(path)


def _write_single_band_raster(path: Path, array: np.ndarray) -> str:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=array.shape[0],
        width=array.shape[1],
        count=1,
        dtype=str(array.dtype),
        transform=from_origin(100, 100, 1, 1),
    ) as dataset:
        dataset.write(array, 1)
    return str(path)


def test_visualization_service_builds_dashboard_with_previews(tmp_path: Path) -> None:
    input_path = _write_multiband_raster(tmp_path / "input.tif")
    raw_prediction_path = _write_single_band_raster(
        tmp_path / "class.tif",
        np.array(
            [
                [0, 1, 1, 2],
                [0, 1, 3, 2],
                [4, 4, 3, 2],
                [4, 4, 3, 0],
            ],
            dtype=np.uint8,
        ),
    )
    mask_path = _write_single_band_raster(
        tmp_path / "mask.tif",
        np.array(
            [
                [0, 1, 1, 0],
                [0, 1, 0, 0],
                [1, 1, 0, 0],
                [1, 0, 0, 0],
            ],
            dtype=np.uint8,
        ),
    )
    confidence_path = _write_single_band_raster(
        tmp_path / "confidence.tif",
        np.array(
            [
                [0.1, 0.4, 0.6, 0.2],
                [0.2, 0.8, 0.7, 0.1],
                [0.9, 0.95, 0.55, 0.15],
                [0.85, 0.25, 0.2, 0.05],
            ],
            dtype=np.float32,
        ),
    )
    report_path = tmp_path / "report.html"
    report_path.write_text("<html><body><h1>Report</h1></body></html>", encoding="utf-8")

    client = LocalVisualizationServiceClient(
        config=VisualizationServiceConfig(
            visualization_output_dir=str(tmp_path / "visualizations"),
            visualization_embed_html_in_response=False,
        )
    )
    result = client.build_visualization(
        request_id="req-viz-001",
        workflow_status="completed",
        user_query="Assess scalp condition and explain the result.",
        task_type="baldness_detection",
        region="scalp",
        crop_type="hair",
        image_path=input_path,
        use_mock=False,
        extra_params={"threshold": 0.5},
        planner_result={"need_report": True},
        executor_result={"tool_name": "build_visualization"},
        model_exists=True,
        model_id=1,
        model_name="baldness-rf",
        model_version="rf-v1",
        model_status="ready",
        artifact_uri="/models/baldness-rf.pkl",
        model_metrics={"miou": 0.91, "source": "integration-test"},
        model_description="Random forest baseline for scalp baldness segmentation.",
        training_triggered=False,
        training_job_id=None,
        training_workflow_id=None,
        training_run_id=None,
        training_task_queue=None,
        training_backend=None,
        inference_result={
            "mask_uri": mask_path,
            "raw_prediction_uri": raw_prediction_path,
            "confidence_map_uri": confidence_path,
            "affected_area": 6.0,
            "confidence": 0.82,
            "class_distribution": [
                {"class_value": 1, "label": "baldness", "count": 4, "ratio": 0.25, "mean_confidence": 0.75}
            ],
            "class_labels": {"1": "baldness"},
            "warnings": ["class semantics loaded from model metadata"],
        },
        rag_result={
            "summary": "Knowledge snippets were retrieved.",
            "sources": ["local://knowledge/baldness"],
            "results": [],
        },
        report_result={
            "report_uri": str(report_path),
            "title": "Baldness report",
        },
        confidence_result={
            "final_confidence": 0.78,
            "final_label": "medium",
            "image_detail": {"warnings": ["review boundary quality"]},
        },
        stage_timings=[
            {"stage": "parse_request", "status": "done", "duration_ms": 1.23, "detail": "baldness_detection"},
            {"stage": "run_inference", "status": "done", "duration_ms": 42.5, "detail": "rf-v1"},
            {"stage": "build_report", "status": "done", "duration_ms": 7.1, "detail": "report-req-viz-001"},
        ],
        errors=[],
        final_state={"status": "completed", "request_id": "req-viz-001"},
    )

    dashboard_path = Path(result.visualization_uri)
    assert dashboard_path.exists()
    assert Path(result.snapshot_path).exists()
    preview_paths = [
        Path(item["preview_uri"])
        for item in result.artifacts
        if item.get("preview_uri")
    ]
    assert preview_paths
    assert all(path.exists() for path in preview_paths)

    html = dashboard_path.read_text(encoding="utf-8")
    assert "产物总览" in html
    assert "req-viz-001" in html
    assert "Baldness report" in html
    assert "类别图例" in html
    assert "内嵌报告预览" in html
    assert "42.50 ms" in html
    assert "Random forest baseline for scalp baldness segmentation." in html
