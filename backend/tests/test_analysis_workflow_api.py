"""Phase-one workflow registration keeps verified inputs and honest planned state."""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import rasterio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from rasterio.transform import from_origin

from api.canonical.router import install_canonical_product_api
from infra.imagery.aoi_band_reader import AoiBandReadError
from infra.imagery.stac_provider import ImagerySearchError
from infra.imagery.crop_spatial import CropInferenceError
from runtime.analysis_workflow_store import AnalysisWorkflowStore


AOI = {
    "geometry": {
        "type": "Polygon",
        "coordinates": [[[100.0, 38.0], [100.01, 38.0], [100.01, 38.01], [100.0, 38.01], [100.0, 38.0]]],
    },
    "source": "drawn",
}
SNAPSHOT = {
    "item_id": "S2-workflow",
    "collection": "sentinel-2-l2a",
    "acquired_at": "2026-09-30T00:00:00Z",
    "selection_token": "signed-selection",
    "asset_fingerprint": "fingerprint",
}


class VerifyingProvider:
    def get_item(self, item_id: str) -> dict:
        return {"id": item_id}

    def validate_selection(self, snapshot, item: dict, geometry: dict):
        if item["id"] != snapshot.item_id or snapshot.selection_token != "signed-selection":
            raise ImagerySearchError("invalid selection")
        assert geometry["type"] == "Polygon"
        return snapshot


def _app(db_path) -> FastAPI:
    app = FastAPI()
    install_canonical_product_api(app, db_path=str(db_path), auth_required=False)
    app.state.sentinel_stac_provider = VerifyingProvider()
    return app


def test_workflow_registers_dependencies_events_and_survives_restart(tmp_path) -> None:
    db_path = tmp_path / "workflow.sqlite3"
    app = _app(db_path)
    with TestClient(app) as client:
        created = client.post("/api/product/v1/analysis-workflows", json={
            "aoi": AOI, "imagery_item_id": "S2-workflow", "imagery_snapshot": SNAPSHOT,
            "requested_task_ids": ["yield"], "start_immediately": False,
        })
        assert created.status_code == 201
        payload = created.json()
        assert payload["status"] == "planned"
        assert payload["requested_task_ids"] == ["yield"]
        assert payload["effective_task_ids"] == ["crop", "lai", "yield"]
        assert [(step["step_id"], step["depends_on"], step["status"]) for step in payload["steps"]] == [
            ("imagery", [], "planned"), ("crop", ["imagery"], "planned"),
            ("lai", ["imagery"], "planned"), ("yield", ["crop", "lai"], "planned"),
        ]
        workflow_id = payload["workflow_id"]
        assert client.get(f"/api/product/v1/analysis-workflows/{workflow_id}").json() == payload
        events = client.get(f"/api/product/v1/analysis-workflows/{workflow_id}/events")
        assert events.status_code == 200
        assert [(event["sequence"], event["kind"]) for event in events.json()["items"]] == [(1, "created")]
        assert app.state.analysis_workflow_store.get(workflow_id, owner_id="another-user") is None

    reloaded = AnalysisWorkflowStore(db_path=str(db_path))
    assert reloaded.get(workflow_id, owner_id="anonymous").status == "planned"
    assert len(reloaded.list_events(workflow_id, owner_id="anonymous")) == 1
    reloaded.close()


def test_workflow_rejects_unverified_or_invalid_task_selection(tmp_path) -> None:
    app = _app(tmp_path / "rejected.sqlite3")
    base = {"aoi": AOI, "imagery_item_id": "S2-workflow", "requested_task_ids": ["crop", "lai"]}
    with TestClient(app) as client:
        missing = client.post("/api/product/v1/analysis-workflows", json=base)
        forged = client.post("/api/product/v1/analysis-workflows", json={
            **base, "imagery_snapshot": {**SNAPSHOT, "selection_token": "forged"},
        })
        duplicates = client.post("/api/product/v1/analysis-workflows", json={
            **base, "imagery_snapshot": SNAPSHOT, "requested_task_ids": ["crop", "crop"],
        })
        empty = client.post("/api/product/v1/analysis-workflows", json={
            **base, "imagery_snapshot": SNAPSHOT, "requested_task_ids": [],
        })
        assert missing.status_code == forged.status_code == 400
        assert duplicates.status_code == empty.status_code == 422
        assert app.state.analysis_workflow_store._db.execute(
            "SELECT COUNT(*) FROM product_analysis_workflows"
        ).fetchone()[0] == 0


def test_standalone_crop_report_is_rendered_from_real_result(tmp_path, monkeypatch) -> None:
    import api.canonical.router as router

    monkeypatch.setattr(router, "verify_crop_model", lambda: tmp_path / "model.h5")
    monkeypatch.setattr(router, "run_crop_spatial_analysis", lambda **_kwargs: {
        "predicted_class": {"class_id": 0, "name_zh": "玉米", "score": 0.8},
        "class_scores": [{"class_id": 0, "name_zh": "玉米", "score": 0.8}],
        "model": {"name": "test model", "sha256": "test digest"},
        "warnings": ["不是逐像元分类图"],
    })
    app = _app(tmp_path / "crop-report.sqlite3")
    app.state.product_artifact_root = tmp_path / "artifacts"
    with TestClient(app) as client:
        response = client.post("/api/product/v1/crop-analyses", json={
            "aoi": AOI, "imagery_item_id": "S2-workflow", "imagery_snapshot": SNAPSHOT,
        })
        assert response.status_code == 202
        analysis_id = response.json()["analysis_id"]
        for _ in range(100):
            result = client.get(f"/api/product/v1/crop-analyses/{analysis_id}").json()
            if result["status"] in {"completed", "failed"}:
                break
            time.sleep(0.05)
        assert result["status"] == "completed"
        report = client.get(result["result"]["report_uri"])
        assert report.status_code == 200
        assert "玉米" in report.text
        assert "不是逐像元分类图" in report.text


def _wait_for_terminal(client: TestClient, workflow_id: str) -> dict:
    for _ in range(100):
        item = client.get(f"/api/product/v1/analysis-workflows/{workflow_id}").json()
        if item["status"] in {"completed", "blocked", "failed"}:
            return item
        time.sleep(0.05)
    raise AssertionError("workflow did not reach a terminal state")


def test_simple_yield_runs_without_apsim_or_manual_dates_and_persists_report(tmp_path, monkeypatch):
    import runtime.analysis_workflow_runner as runner
    from runtime.simple_yield import SimpleYieldError
    attempts = []
    def image(**kwargs):
        Path(kwargs['output_path']).write_bytes(b'shared reflectance')
        return kwargs['output_path']
    def simple(workflow, cache, progress):
        attempts.append(workflow.yield_inputs.confirmed_crop_class_id)
        if workflow.yield_inputs.confirmed_crop_class_id is None:
            raise SimpleYieldError('crop_confirmation_required', '请确认本季地块作物')
        assert workflow.yield_inputs.sowing_date is None and workflow.yield_inputs.field_dataset_id is None
        progress('试验数据已准备', 90)
        return {'experimental': True, 'locally_calibrated': False, 'estimated_yield_t_ha': 4.2,
                'parameter_scenario_range_t_ha': [3.2, 5.5], 'crop_label': '玉米',
                'season': {'start': '2025-04-20', 'end': '2025-09-01', 'observations': 10},
                'uncertainty_note': '未用本地实收数据校准，范围不是置信区间'}
    monkeypatch.setattr(runner, 'read_prosail_reflectance_aoi', image)
    monkeypatch.setattr(runner, 'run_crop_spatial_analysis', lambda **kwargs: {'predicted_class': {'class_id': 0, 'name_zh': '玉米', 'score': 0.5}})
    monkeypatch.setattr(runner, 'run_simple_yield', simple)
    monkeypatch.setattr(runner, 'run_lai_html_report', lambda **kwargs: pytest.fail('simple yield must not require LAI inversion'))
    monkeypatch.setattr(runner, 'run_field_yield', lambda *args: pytest.fail('simple yield must not start APSIM'))
    app = _app(tmp_path / 'simple.sqlite3')
    app.state.product_artifact_root = tmp_path / 'artifacts'
    with TestClient(app) as client:
        response = client.post('/api/product/v1/analysis-workflows', json={'aoi': AOI, 'imagery_item_id': 'S2-workflow', 'imagery_snapshot': SNAPSHOT, 'requested_task_ids': ['yield_simple']})
        assert response.status_code == 201
        workflow_id = response.json()['workflow_id']
        blocked = _wait_for_terminal(client, workflow_id)
        assert blocked['status'] == 'blocked'
        assert blocked['effective_task_ids'] == ['crop', 'yield_simple']
        assert [step['step_id'] for step in blocked['steps']] == ['imagery', 'crop', 'yield_simple']
        invalid = client.put(f'/api/product/v1/analysis-workflows/{workflow_id}/yield-inputs', json={'yield_inputs': {'confirmed_crop_class_id': 2}})
        assert invalid.status_code == 409
        assert client.get(f'/api/product/v1/analysis-workflows/{workflow_id}').json()['yield_inputs']['confirmed_crop_class_id'] is None
        confirmed = client.put(f'/api/product/v1/analysis-workflows/{workflow_id}/yield-inputs', json={'yield_inputs': {'confirmed_crop_class_id': 0}})
        assert confirmed.status_code == 200
        completed = _wait_for_terminal(client, workflow_id)
        assert completed['status'] == 'completed'
        result = completed['steps'][-1]['result']
        assert attempts == [None, 0]
        assert result['estimated_yield_t_ha'] == 4.2
        rendered = client.get(result['report_uri'])
        assert rendered.status_code == 200 and '粮食干重' in rendered.text and '置信区间' in rendered.text
        assert client.get(completed['report_uri']).status_code == 200
        unchanged = client.put(f'/api/product/v1/analysis-workflows/{workflow_id}/yield-inputs', json={'yield_inputs': {'confirmed_crop_class_id': 0}})
        assert unchanged.status_code == 200 and attempts == [None, 0]
        changed = client.put(f'/api/product/v1/analysis-workflows/{workflow_id}/yield-inputs', json={'yield_inputs': {'confirmed_crop_class_id': 3}})
        assert changed.status_code == 409
        app.state.product_auth_required = True
        app.state.product_auth_token = 'different-owner'
        assert client.get(result['report_uri'], headers={'Authorization': 'Bearer different-owner'}).status_code == 404


@pytest.mark.parametrize("failed_task", ["crop", "lai"])
def test_workflow_shares_one_image_and_preserves_successful_step_on_retry(tmp_path, monkeypatch, failed_task) -> None:
    import runtime.analysis_workflow_runner as runner

    reads = []
    crop_attempts = []
    lai_attempts = []

    def fake_read(*, output_path, progress_callback, **_kwargs):
        reads.append(output_path)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(output_path, "w", driver="GTiff", width=4, height=4,
                           count=5, dtype="float32", crs="EPSG:4326",
                           transform=from_origin(100, 38.01, 0.0025, 0.0025), nodata=0) as dst:
            dst.write(np.full((5, 4, 4), 0.2, dtype="float32"))
        progress_callback("五波段影像已就绪", 100)
        return output_path

    def fake_crop(*, reflectance_path, **_kwargs):
        assert reflectance_path == reads[0]
        crop_attempts.append(reflectance_path)
        if failed_task == "crop" and len(crop_attempts) == 1:
            raise CropInferenceError("测试作物识别失败")
        return {"predicted_class": {"class_id": 0, "name": "Corn", "name_zh": "玉米", "score": 0.7},
                "model": {"name": "test", "sha256": "test"}}

    def fake_lai(*, image_path, artifact_output_dir, progress_callback, scene_constraints):
        assert Path(image_path) == reads[0]
        lai_attempts.append(image_path)
        if failed_task == "lai" and len(lai_attempts) == 1:
            return SimpleNamespace(status="error", summary="测试 LAI 失败", payload={}), []
        directory = Path(artifact_output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        report = directory / "report.html"
        raster = directory / "lai.tif"
        preview = directory / "preview.png"
        report.write_text("<html><body>LAI</body></html>", encoding="utf-8")
        preview.write_bytes(b"\x89PNG\r\n\x1a\npreview")
        with rasterio.open(raster, "w", driver="GTiff", width=4, height=4,
                           count=1, dtype="float32", crs="EPSG:4326",
                           transform=from_origin(100, 38.01, 0.0025, 0.0025), nodata=-9999) as dst:
            dst.write(np.full((4, 4), 2.5, dtype="float32"), 1)
        progress_callback(16, 16)
        payload = {"report_path": str(report), "lai_raster_path": str(raster),
                   "lai_preview_path": str(preview), "lai_mean": 2.5, "vegetation_ratio": 80.0,
                   "bounds_wgs84": [100, 38, 100.01, 38.01],
                   "color_scale": [[0, "#000000"], [7, "#ffffff"]]}
        artifacts = [SimpleNamespace(pack_name="prosail", artifact_type=kind, title=kind,
                                     uri=str(path), content=None)
                     for kind, path in (("lai_html_report", report), ("lai_raster", raster),
                                        ("lai_preview", preview))]
        return SimpleNamespace(status="success", summary="LAI complete", payload=payload), artifacts

    monkeypatch.setattr(runner, "read_prosail_reflectance_aoi", fake_read)
    monkeypatch.setattr(runner, "run_crop_spatial_analysis", fake_crop)
    monkeypatch.setattr(runner, "run_lai_html_report", fake_lai)
    app = _app(tmp_path / "execution.sqlite3")
    app.state.product_artifact_root = tmp_path / "artifacts"
    with TestClient(app) as client:
        created = client.post("/api/product/v1/analysis-workflows", json={
            "aoi": AOI, "imagery_item_id": "S2-workflow", "imagery_snapshot": SNAPSHOT,
            "requested_task_ids": ["crop", "lai", "growth", "yield"],
        })
        assert created.status_code == 201
        workflow_id = created.json()["workflow_id"]
        failed = _wait_for_terminal(client, workflow_id)
        steps = {step["step_id"]: step for step in failed["steps"]}
        assert failed["status"] == "failed"
        assert steps["imagery"]["status"] == "completed"
        assert steps[failed_task]["status"] == "failed"
        successful_task = "lai" if failed_task == "crop" else "crop"
        assert steps[successful_task]["status"] == "completed"
        assert steps["growth"]["status"] == ("completed" if failed_task == "crop" else "blocked")
        assert steps["yield"]["status"] == "blocked"
        if failed_task == "crop":
            assert steps["lai"]["result"]["observation_at"] == SNAPSHOT["acquired_at"]
            assert steps["lai"]["result"]["quality"]["valid_pixel_count"] == 16
            assert app.state.lai_analysis_store.get(steps["lai"]["analysis_id"]).status == "completed"
            assert steps["growth"]["result"]["vegetation_ratio"] == 80.0
        successful_id = steps[successful_task]["analysis_id"]

        retried = client.post(f"/api/product/v1/analysis-workflows/{workflow_id}/retry",
                              json={"step_id": failed_task})
        assert retried.status_code == 202
        result = _wait_for_terminal(client, workflow_id)
        new_steps = {step["step_id"]: step for step in result["steps"]}
        assert result["status"] == "blocked"  # APSIM input contract is not connected yet.
        assert new_steps["crop"]["status"] == "completed"
        assert new_steps["lai"]["status"] == "completed"
        assert new_steps["growth"]["status"] == "completed"
        assert new_steps[successful_task]["analysis_id"] == successful_id
        assert new_steps[failed_task]["analysis_id"] != steps[failed_task]["analysis_id"]
        assert len(reads) == 1
        assert len(crop_attempts) == (2 if failed_task == "crop" else 1)
        assert len(lai_attempts) == (2 if failed_task == "lai" else 1)
        assert result["report_uri"].endswith("/render")
        for step_id in ("crop", "lai", "growth"):
            uri = new_steps[step_id]["result"]["report_uri"]
            assert uri.endswith("/render")
            report_response = client.get(uri)
            assert report_response.status_code == 200
            assert "text/html" in report_response.headers["content-type"]
        summary = client.get(result["report_uri"])
        assert summary.status_code == 200
        assert "农作物识别" in summary.text
        data = client.get(result["report_data_uri"])
        assert data.status_code == 200
        assert data.json()["report_version"] == "map-report-v2"
        app.state.product_auth_required = True
        app.state.product_auth_token = "other-principal-key"
        assert client.get(result["report_uri"], headers={"Authorization": "Bearer other-principal-key"}).status_code == 404
        app.state.product_auth_required = False
        events = client.get(f"/api/product/v1/analysis-workflows/{workflow_id}/events").json()["items"]
        assert any(event["step_id"] == failed_task and event["kind"] == "step_updated" for event in events)


def test_imagery_failure_can_retry_without_creating_a_child_before_data_exists(tmp_path, monkeypatch) -> None:
    import runtime.analysis_workflow_runner as runner

    reads = []

    def fake_read(*, output_path, **_kwargs):
        reads.append(output_path)
        if len(reads) == 1:
            raise AoiBandReadError("远端影像暂时不可用")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"shared-image")
        return output_path

    def fake_crop(*, reflectance_path, **_kwargs):
        assert reflectance_path.read_bytes() == b"shared-image"
        return {"predicted_class": {"class_id": 0, "name": "Corn", "name_zh": "玉米", "score": 0.8}}

    monkeypatch.setattr(runner, "read_prosail_reflectance_aoi", fake_read)
    monkeypatch.setattr(runner, "run_crop_spatial_analysis", fake_crop)
    app = _app(tmp_path / "image-retry.sqlite3")
    app.state.product_artifact_root = tmp_path / "artifacts"
    with TestClient(app) as client:
        created = client.post("/api/product/v1/analysis-workflows", json={
            "aoi": AOI, "imagery_item_id": "S2-workflow", "imagery_snapshot": SNAPSHOT,
            "requested_task_ids": ["crop"],
        })
        workflow_id = created.json()["workflow_id"]
        failed = _wait_for_terminal(client, workflow_id)
        assert failed["status"] == "failed"
        assert next(step for step in failed["steps"] if step["step_id"] == "crop")["analysis_id"] is None

        assert client.post(f"/api/product/v1/analysis-workflows/{workflow_id}/retry",
                           json={"step_id": "imagery"}).status_code == 202
        completed = _wait_for_terminal(client, workflow_id)
        assert completed["status"] == "completed"
        assert len(reads) == 2
        assert next(step for step in completed["steps"] if step["step_id"] == "crop")["status"] == "completed"


def test_running_workflow_is_marked_failed_after_service_restart(tmp_path) -> None:
    app = _app(tmp_path / "restart.sqlite3")
    with TestClient(app) as client:
        response = client.post("/api/product/v1/analysis-workflows", json={
            "aoi": AOI, "imagery_item_id": "S2-workflow", "imagery_snapshot": SNAPSHOT,
            "requested_task_ids": ["crop"], "start_immediately": False,
        })
        workflow_id = response.json()["workflow_id"]
        store = app.state.analysis_workflow_store
        store.update_status(workflow_id, owner_id="anonymous", status="running", detail="正在执行")
        store.update_step(workflow_id, "imagery", owner_id="anonymous", status="running", detail="正在读取")

    reopened = AnalysisWorkflowStore(db_path=str(tmp_path / "restart.sqlite3"))
    workflow = reopened.get(workflow_id, owner_id="anonymous")
    assert workflow.status == "failed"
    assert workflow.steps[0].status == "failed"
    assert reopened.list_events(workflow_id, owner_id="anonymous")[-1].kind == "status_updated"
    reopened.close()
