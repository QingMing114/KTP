"""Map LAI automatic configuration reaches the real LUT inversion and persists."""
from types import SimpleNamespace

import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from pydantic import ValidationError
from rasterio.transform import from_origin

from schemas.runtime import SceneParameters
from test_analysis_workflow_api import AOI, SNAPSHOT, _app, _wait_for_terminal


class SceneProvider:
    def __init__(self, mode="llm"):
        self.mode = mode
        self.prompts = []

    def generate_structured(self, *, system_prompt, user_prompt, response_model):
        assert response_model is SceneParameters
        self.prompts.append(user_prompt)
        if self.mode == "outage":
            raise RuntimeError("test model unavailable")
        return response_model(
            lai_range=[9, 10] if self.mode == "no_matches" else [8, -1] if self.mode == "invalid" else [4, 5],
            confidence=0.9, crop_type="玉米", month=9, reasoning="依据当前影像与作物信息配置。",
        )


def setup_app(tmp_path, monkeypatch, provider):
    import runtime.analysis_workflow_runner as runner

    values = np.array([.08, .10, .12, .18, .22], dtype=np.float32)

    def read_image(*, output_path, **kwargs):
        with rasterio.open(output_path, "w", driver="GTiff", height=4, width=4, count=5,
                           dtype="float32", crs="EPSG:4326", transform=from_origin(100, 38.01, .0025, .0025)) as ds:
            ds.write(np.broadcast_to(values[:, None, None], (5, 4, 4)).copy())
        return output_path

    lut = np.zeros((30, 13), dtype=np.float32)
    lut[:10, 0], lut[10:, 0] = 1., 4.5
    for i, col in enumerate((1, 2, 3, 6, 7)):
        lut[:10, col], lut[10:, col] = values[i], values[i] + .02
    lut[:, 9:13] = [50, 55, .5, 1.5]
    lut_path = tmp_path / "lut.txt"
    np.savetxt(lut_path, lut)
    monkeypatch.setenv("LAI_LUT_PATH", str(lut_path))
    monkeypatch.setenv("LAI_REPORT_OUTPUT_DIR", str(tmp_path / "reports"))
    monkeypatch.setattr(runner, "read_prosail_reflectance_aoi", read_image)
    monkeypatch.setattr("runtime.crop_classification.run_crop_spatial_analysis", lambda **kwargs: {
        "predicted_class": {"class_id": 0, "name_zh": "玉米", "score": .8},
    })
    app = _app(tmp_path / "test.sqlite3")
    app.state.runtime_engine = SimpleNamespace(llm_provider=provider)
    app.state.product_artifact_root = tmp_path / "artifacts"
    return app


@pytest.mark.parametrize("mode,source,application,expected", [
    ("llm", "llm", "applied", 4.5),
    ("outage", "rule_based", "applied", 4.5),
    ("invalid", "rule_based", "applied", 4.5),
    ("no_matches", "llm", "fallback", 1.),
])
def test_map_model_parameters_reach_real_inversion(tmp_path, monkeypatch, mode, source, application, expected):
    provider = SceneProvider(mode)
    app = setup_app(tmp_path, monkeypatch, provider)
    with TestClient(app) as client:
        response = client.post("/api/product/v1/analysis-workflows", json={
            "aoi": AOI, "imagery_item_id": SNAPSHOT["item_id"], "imagery_snapshot": SNAPSHOT,
            "requested_task_ids": ["crop", "lai"], "lai_query": "请为玉米自动配置反演参数",
        })
        assert response.status_code == 201, response.text
        workflow = _wait_for_terminal(client, response.json()["workflow_id"])
        assert workflow["status"] == "completed", workflow
        lai = next(s for s in workflow["steps"] if s["step_id"] == "lai")
        result = lai["result"]
        assert result["lai_mean"] == expected
        assert result["scene_parameters"]["source"] == source
        assert result["constraint_application"]["status"] == application
        assert len(provider.prompts) == 1
        assert "2026-09-30" in provider.prompts[0] and "玉米" in provider.prompts[0]
        assert "aoi_bounds_wgs84" in provider.prompts[0]
        assert "signed-selection" not in provider.prompts[0]
        assert result["scene_parameters"]["context"]["crop_prediction"]["score"] == .8
        child = app.state.lai_analysis_store.get(lai["analysis_id"])
        assert child.result["scene_parameters"] == result["scene_parameters"]
        persisted = client.get(result["report_data_uri"]).json()
        assert persisted["result"]["constraint_application"] == result["constraint_application"]
        assert "constraint_application" in client.get(result["report_uri"]).text
        assert "场景参数来源" in client.get(workflow["report_uri"]).text


def test_lai_only_retry_reuses_persisted_model_configuration(tmp_path, monkeypatch):
    import runtime.analysis_workflow_runner as runner
    provider = SceneProvider()
    app = setup_app(tmp_path, monkeypatch, provider)
    real_report = runner.run_lai_html_report
    attempts = []

    def fail_once(**kwargs):
        attempts.append(kwargs["scene_constraints"])
        if len(attempts) == 1:
            return SimpleNamespace(status="error", summary="test failure"), []
        return real_report(**kwargs)

    monkeypatch.setattr(runner, "run_lai_html_report", fail_once)
    with TestClient(app) as client:
        response = client.post("/api/product/v1/analysis-workflows", json={
            "aoi": AOI, "imagery_item_id": SNAPSHOT["item_id"], "imagery_snapshot": SNAPSHOT,
            "requested_task_ids": ["lai"], "lai_query": "这是一块玉米田",
        })
        workflow_id = response.json()["workflow_id"]
        assert _wait_for_terminal(client, workflow_id)["status"] == "failed"
        assert client.post(f"/api/product/v1/analysis-workflows/{workflow_id}/retry", json={"step_id": "lai"}).status_code == 202
        completed = _wait_for_terminal(client, workflow_id)
        assert completed["status"] == "completed"
        assert len(provider.prompts) == 1
        assert attempts == [{"lai_range": [4., 5.]}] * 2
        assert completed["lai_query"] == "这是一块玉米田"
        assert '"crop_prediction": null' in provider.prompts[0]


@pytest.mark.parametrize("values", [
    {"lai_range": [8, -1]}, {"cab_range": [-2, 101]}, {"lidfa_range": [0, 91]},
    {"psoil_range": [0, float("nan")]}, {"confidence": 2}, {"month": 99},
])
def test_invalid_scene_parameters_are_rejected(values):
    with pytest.raises(ValidationError):
        SceneParameters(**values)


def test_fallback_uses_observation_month_and_structured_crop():
    from v2.runtime.scene_extractor import extract_scene_parameters
    scene = extract_scene_parameters(llm_provider=None, query="7月提到过反演", image_path=None,
                                     region=None, crop_type="玉米", scene_context={"acquired_at": "2026-09-30"})
    assert scene.month == 9
    assert scene.lai_range == (1.5, 5.)
    assert scene.source == "rule_based"


def test_scene_model_prompt_uses_scene_example_instead_of_tool_call():
    from infra.llm.provider import _build_structured_prompt
    prompt = _build_structured_prompt(user_prompt="配置当前影像参数", response_model=SceneParameters)
    assert '"lai_range": [3, 7]' in prompt
    assert "prosail.simulation" not in prompt


def test_draft_description_from_another_aoi_is_not_reused():
    from runtime.workspace_lai import workspace_lai_query
    from schemas.workspace import WorkspaceContext
    context = WorkspaceContext(workspace_id="w", revision=1, aoi=AOI, imagery_item_id="current")
    stale = SimpleNamespace(status="completed", input_message="旧地块玉米", input_context=SimpleNamespace(extra_params={
        "workspace": {"workspace_id": "w", "execution_mode": "live", "imagery_item_id": "current", "aoi": {"geometry": {}}},
    }), product_parts=[{"type": "analysis_plan", "data": {"effective_task_ids": ["lai"]}}])
    assert workspace_lai_query("执行当前地块", context, [stale]) == "执行当前地块"
