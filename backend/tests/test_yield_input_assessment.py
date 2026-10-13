"""A field yield cannot be reported from a crop label and one LAI value alone."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from runtime.analysis_workflow_runner import _finish
from runtime.yield_input_assessment import assess_yield_inputs
from schemas.analysis_workflow import CreateAnalysisWorkflowRequest, YieldAgronomicInputs

from test_analysis_workflow_api import AOI, SNAPSHOT, _app


def _workflow(tmp_path, *, class_id=0, score=0.7, runner_up=0.1, valid=80, total=100):
    app = _app(tmp_path / "yield-gate.sqlite3")
    store = app.state.analysis_workflow_store
    request = CreateAnalysisWorkflowRequest.model_validate({
        "aoi": AOI, "imagery_item_id": "S2-workflow", "imagery_snapshot": SNAPSHOT,
        "requested_task_ids": ["yield"], "start_immediately": False,
    })
    workflow = store.create(request, owner_id="anonymous")
    scores = [{"class_id": i, "score": runner_up if i != class_id else score} for i in range(6)]
    store.update_step(workflow.workflow_id, "crop", owner_id="anonymous", status="completed",
                      result={"predicted_class": {"class_id": class_id, "score": score},
                              "class_scores": scores})
    store.update_step(workflow.workflow_id, "lai", owner_id="anonymous", status="completed",
                      result={"observation_at": SNAPSHOT["acquired_at"], "lai_mean": 2.5,
                              "quality": {"valid_pixel_count": valid, "total_pixel_count": total,
                                          "valid_pixel_fraction": valid / total},
                              "lai_raster_artifact_id": "lai-raster"})
    return app, store, workflow.workflow_id


@pytest.mark.parametrize(("class_id", "expected"), [
    (0, "maize"), (1, None), (2, "soybean"),
    (3, "wheat"), (4, "wheat"), (5, None),
])
def test_exact_crop_mapping_and_unsupported_crops(tmp_path, class_id, expected):
    app, store, workflow_id = _workflow(tmp_path, class_id=class_id)
    assessment = assess_yield_inputs(store.get(workflow_id, owner_id="anonymous"))
    assert assessment.resolved_crop == expected
    codes = {issue.code for issue in assessment.issues}
    assert ("crop_model_unsupported" in codes) == (expected is None)
    assert "daily_weather_unavailable" in codes
    assert assessment.status == "blocked"
    store.close()


def test_low_crop_score_and_lai_quality_require_review_without_yield(tmp_path):
    app, store, workflow_id = _workflow(tmp_path, score=0.32, runner_up=0.29, valid=10)
    _finish(store, workflow_id, "anonymous")
    workflow = store.get(workflow_id, owner_id="anonymous")
    result = next(step.result for step in workflow.steps if step.step_id == "yield")
    codes = {issue["code"] for issue in result["input_assessment"]["issues"]}
    assert {"crop_confirmation_required", "lai_quality_low", "cultivar_missing",
            "sowing_date_missing", "daily_weather_unavailable", "soil_profile_unavailable",
            "management_unavailable", "apsim_runtime_unverified", "lai_constraint_unavailable"} <= codes
    assert workflow.status == "blocked"
    assert "estimated_yield_t_ha" not in result
    store.close()


def test_yield_inputs_update_is_owner_scoped_and_reassessed(tmp_path):
    app, store, workflow_id = _workflow(tmp_path, score=0.32, runner_up=0.29)
    app.state.product_artifact_root = tmp_path / "artifacts"
    _finish(store, workflow_id, "anonymous")
    with TestClient(app) as client:
        invalid = client.put(f"/api/product/v1/analysis-workflows/{workflow_id}/yield-inputs",
                             json={"yield_inputs": {"confirmed_crop_class_id": 6}})
        assert invalid.status_code == 422
        updated = client.put(f"/api/product/v1/analysis-workflows/{workflow_id}/yield-inputs",
                             json={"yield_inputs": {"confirmed_crop_class_id": 2,
                                                    "cultivar": "local verified cultivar",
                                                    "sowing_date": "2026-05-01"}})
        assert updated.status_code == 200
        payload = updated.json()
        assessment = next(step["result"]["input_assessment"] for step in payload["steps"]
                          if step["step_id"] == "yield")
        codes = {issue["code"] for issue in assessment["issues"]}
        assert assessment["resolved_crop"] == "soybean"
        assert assessment["crop_source"] == "user_confirmed"
        assert not {"crop_confirmation_required", "cultivar_missing", "sowing_date_missing"} & codes
        assert "daily_weather_unavailable" in codes
        assert payload["status"] == "blocked"
        assert payload["report_uri"].endswith("/render")
        summary = client.get(payload["report_uri"])
        assert summary.status_code == 200
        assert "产量估计" in summary.text
        assert store.get(workflow_id, owner_id="another-user") is None
        assert len(store.list_events(workflow_id, owner_id="anonymous")) > 4


def test_sowing_after_observation_is_rejected(tmp_path):
    app, store, workflow_id = _workflow(tmp_path)
    store.update_yield_inputs(workflow_id, owner_id="anonymous", inputs=YieldAgronomicInputs(
        confirmed_crop_class_id=0, cultivar="test", sowing_date=date(2026, 10, 1),
    ))
    assessment = assess_yield_inputs(store.get(workflow_id, owner_id="anonymous"))
    assert "sowing_after_observation" in {issue.code for issue in assessment.issues}
    store.close()
