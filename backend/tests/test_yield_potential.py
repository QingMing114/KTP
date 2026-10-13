"""The lightweight canopy task must never claim absolute grain yield."""

from pathlib import Path

import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_origin

from runtime.analysis_workflow_runner import _finish, ensure_workflow_reports
from runtime.lai_quality import assess_lai_raster_quality
from runtime.yield_potential import YieldPotentialError, estimate_yield_potential
from schemas.analysis_workflow import CreateAnalysisWorkflowRequest

from test_analysis_workflow_api import AOI, SNAPSHOT, _app


def test_lai_coverage_uses_polygon_pixels_instead_of_bounding_rectangle(tmp_path):
    raster_path = tmp_path / "lai.tif"
    with rasterio.open(raster_path, "w", driver="GTiff", height=10, width=10,
                       count=1, dtype="float32", crs="EPSG:4326",
                       transform=from_origin(0, 10, 1, 1), nodata=0) as dataset:
        dataset.write(np.ones((10, 10), dtype="float32"), 1)
    triangle = {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [0, 10], [0, 0]]]}

    quality = assess_lai_raster_quality(raster_path, triangle)

    assert 16 <= quality["total_pixel_count"] < 100
    assert quality["valid_pixel_count"] == quality["total_pixel_count"]
    assert quality["valid_pixel_fraction"] == 1.0
    assert quality["quality_basis"] == "aoi_pixels"
    assert quality["bounding_pixel_count"] == 100


def _ready_workflow(tmp_path: Path):
    app = _app(tmp_path / "potential.sqlite3")
    store = app.state.analysis_workflow_store
    workflow = store.create(CreateAnalysisWorkflowRequest.model_validate({
        "aoi": AOI, "imagery_item_id": "S2-workflow", "imagery_snapshot": SNAPSHOT,
        "requested_task_ids": ["potential"], "start_immediately": False,
    }), owner_id="anonymous")
    store.update_step(workflow.workflow_id, "crop", owner_id="anonymous", status="completed",
                      result={"predicted_class": {"class_id": 0, "name_zh": "玉米", "score": 0.8}})
    store.update_step(workflow.workflow_id, "lai", owner_id="anonymous", status="completed",
                      result={"observation_at": SNAPSHOT["acquired_at"], "lai_mean": 2.5,
                              "quality": {"valid_pixel_count": 100, "valid_pixel_fraction": 1.0}})
    image = tmp_path / "artifacts" / "workflows" / workflow.workflow_id / "reflectance.tif"
    image.parent.mkdir(parents=True)
    bands = np.ones((5, 10, 10), dtype="float32") * 0.1
    bands[2] = 0.1  # B04 red
    bands[4] = 0.3  # B08 NIR: NDVI = 0.5
    with rasterio.open(image, "w", driver="GTiff", height=10, width=10, count=5,
                       dtype="float32", crs="EPSG:32647", transform=from_origin(0, 200, 20, 20),
                       nodata=0) as dataset:
        dataset.write(bands)
    return app, store, workflow.workflow_id, image


def test_potential_uses_real_bands_and_never_returns_yield_t_ha(tmp_path):
    app, store, workflow_id, image = _ready_workflow(tmp_path)
    workflow = store.get(workflow_id, owner_id="anonymous")
    result = estimate_yield_potential(workflow, image)
    assert result["ndvi_median"] == pytest.approx(0.5)
    assert 0 < result["canopy_index"] < 100
    assert result["output_type"] == "uncalibrated_canopy_index"
    assert not any("yield_t_ha" in key for key in result)

    _finish(store, workflow_id, "anonymous", artifact_root=tmp_path / "artifacts",
            artifacts=app.state.product_artifact_store)
    updated = store.get(workflow_id, owner_id="anonymous")
    potential = next(step for step in updated.steps if step.step_id == "potential")
    assert updated.status == "completed"
    assert potential.status == "completed"
    assert potential.result["canopy_index"] == result["canopy_index"]
    assert potential.result["report_uri"].startswith("/api/product/v1/artifacts/")
    assert potential.result["report_uri"].endswith("/render")
    app.state.product_artifact_root = tmp_path / "artifacts"
    with TestClient(app) as client:
        report = client.get(potential.result["report_uri"])
        assert report.status_code == 200
        assert "冠层指数" in report.text
    store.close()


def test_low_quality_and_mismatched_date_cannot_produce_index(tmp_path):
    _app_instance, store, workflow_id, image = _ready_workflow(tmp_path)
    store.update_step(workflow_id, "lai", owner_id="anonymous", status="completed",
                      result={"observation_at": SNAPSHOT["acquired_at"], "lai_mean": 2.5,
                              "quality": {"valid_pixel_count": 10, "valid_pixel_fraction": 0.1}})
    with pytest.raises(YieldPotentialError, match="有效像元"):
        estimate_yield_potential(store.get(workflow_id, owner_id="anonymous"), image)
    store.update_step(workflow_id, "lai", owner_id="anonymous", status="completed",
                      result={"observation_at": "2024-01-01T00:00:00Z", "lai_mean": 2.5,
                              "quality": {"valid_pixel_count": 100, "valid_pixel_fraction": 1.0}})
    with pytest.raises(YieldPotentialError, match="观测日期"):
        estimate_yield_potential(store.get(workflow_id, owner_id="anonymous"), image)
    store.close()


def test_bare_soil_signal_is_not_mistaken_for_zero_yield(tmp_path):
    _app_instance, store, workflow_id, image = _ready_workflow(tmp_path)
    with rasterio.open(image, "r+") as dataset:
        dataset.write(np.ones((10, 10), dtype="float32") * 0.1, 5)
    result = estimate_yield_potential(store.get(workflow_id, owner_id="anonymous"), image)
    assert result["canopy_index"] == 0
    assert "不代表实际产量为 0" in result["signal_warning"]
    assert "yield_t_ha" not in result
    store.close()


def test_historical_potential_report_link_is_repaired_without_reinference(tmp_path):
    app, store, workflow_id, _image = _ready_workflow(tmp_path)
    store.update_step(workflow_id, "potential", owner_id="anonymous", status="completed",
                      result={"canopy_index": 41.9, "report_artifact_id": "art_old",
                              "report_uri": "/api/product/v1/artifacts/art_old/content"})
    store.update_status(workflow_id, owner_id="anonymous", status="completed", detail="完成")

    ensure_workflow_reports(store, workflow_id, "anonymous", tmp_path / "artifacts",
                            app.state.product_artifact_store)

    updated = store.get(workflow_id, owner_id="anonymous")
    potential = next(step for step in updated.steps if step.step_id == "potential")
    assert potential.result["report_uri"].endswith("/render")
    assert potential.result["report_data_uri"].endswith("/content")
    assert updated.report_uri.endswith("/render")
    store.close()
