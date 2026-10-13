"""The demo is complete, repeatable, owner-scoped and never a live fallback."""
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.canonical.router import install_canonical_product_api
from infra.imagery.stac_provider import ImagerySearchError
from runtime.yield_demo import build_yield_demo, run_yield_demo
from v2.runtime.store import InMemoryRuntimeStore

AOI = {"geometry": {"type": "Polygon", "coordinates": [[[100,38],[100.01,38],[100.01,38.01],[100,38.01],[100,38]]]}, "source": "drawn"}
SNAPSHOT = {"item_id": "demo-scene", "collection": "sentinel-2-l2a", "acquired_at": "2026-09-10T00:00:00Z"}


class OfflineProvider:
    def get_item(self, item_id):
        raise ImagerySearchError("offline; live imagery must fail")


def app_for_demo(tmp_path, monkeypatch):
    import runtime.analysis_workflow_runner as runner
    monkeypatch.setattr(runner, "run_yield_demo", lambda workflow, **kwargs: run_yield_demo(workflow, step_delay=0, **kwargs))
    app = FastAPI()
    install_canonical_product_api(app, db_path=str(tmp_path / "demo.sqlite3"), auth_required=False)
    app.state.product_artifact_root = tmp_path / "artifacts"
    app.state.sentinel_stac_provider = OfflineProvider()
    app.state.runtime_engine = SimpleNamespace(llm_provider=None)
    app.state.runtime_store = InMemoryRuntimeStore()
    app.state.product_auth_token = "another-owner-key"
    return app


@pytest.mark.parametrize("crop,expected", [("wheat",6.2),("maize",9.1)])
def test_demo_series_units_and_presets(crop, expected):
    result = build_yield_demo(crop, SNAPSHOT["acquired_at"], 10)
    assert result == build_yield_demo(crop, SNAPSHOT["acquired_at"], 10)
    assert result["simulated"] and result["apsim_executed"] is False
    assert result["estimated_yield_t_ha"] == expected
    assert result["estimated_total_t"] == round(expected * 10, 2)
    ts = result["timeseries"]
    assert len(set(map(len, ts.values()))) == 1 and len(ts["dates"]) > 100
    assert ts["dates"][0] == result["season"]["start"]
    assert ts["dates"][-1] == result["season"]["end"] < SNAPSHOT["acquired_at"][:10]
    assert max(ts["grain_wt"]) * 0.01 == pytest.approx(expected)
    assert all(0 <= grain <= bio for grain, bio in zip(ts["grain_wt"],ts["biomass"]))


def wait_workflow(client, workflow_id):
    for _ in range(150):
        response = client.get(f"/api/product/v1/analysis-workflows/{workflow_id}")
        assert response.status_code == 200, response.text
        result = response.json()
        if result["status"] in {"completed","failed","blocked"}:
            return result
        time.sleep(0.02)
    raise AssertionError("demo did not finish")


@pytest.mark.parametrize("task,crop", [("yield_simple","wheat"),("yield_simple","maize"),("yield","wheat"),("yield","maize")])
def test_demo_workflow_and_apsim_template_report_without_external_inputs(tmp_path, monkeypatch, task, crop):
    app = app_for_demo(tmp_path, monkeypatch)
    with TestClient(app) as client:
        body = {"aoi":AOI,"imagery_item_id":SNAPSHOT["item_id"],"imagery_snapshot":SNAPSHOT,
                "requested_task_ids":[task],"data_mode":"demo","demo_crop":crop,"start_immediately":False}
        created = client.post("/api/product/v1/analysis-workflows", json=body,headers={"Idempotency-Key":"demo-once"})
        assert created.status_code == 201, created.text
        workflow_id = created.json()["workflow_id"]
        replay = client.post("/api/product/v1/analysis-workflows",json=body,headers={"Idempotency-Key":"demo-once"})
        assert replay.json()["workflow_id"] == workflow_id
        assert client.post(f"/api/product/v1/analysis-workflows/{workflow_id}/start").status_code == 202
        workflow = wait_workflow(client,workflow_id)
        assert workflow["status"] == "completed" and workflow["data_mode"] == "demo"
        assert all(step["status"] == "completed" and step["result"]["simulated"] for step in workflow["steps"])
        result = next(step["result"] for step in workflow["steps"] if step["step_id"] == task)
        report = client.get(result["report_uri"])
        assert report.status_code == 200
        for text in ["APSIM 模板","模拟数据","未运行 APSIM","LAI 时序","生物量","子粒重","生长阶段时间轴",f'{result["estimated_yield_t_ha"]:.3f}']:
            assert text in report.text
        assert "<script src=" not in report.text
        data = client.get(result["report_data_uri"])
        assert data.status_code == 200
        assert data.json()["result"]["timeseries"] == result["timeseries"]
        assert data.json()["result"]["estimated_yield_t_ha"] == result["estimated_yield_t_ha"]
        assert client.get(workflow["report_uri"]).status_code == 200
        for step in workflow["steps"]:
            assert client.get(step["result"]["report_uri"]).status_code == 200
            assert client.get(step["result"]["report_uri"],headers={"Authorization":"Bearer another-owner-key"}).status_code == 404
        for uri in [result["report_uri"],result["report_data_uri"],workflow["report_uri"],f"/api/product/v1/analysis-workflows/{workflow_id}"]:
            assert client.get(uri,headers={"Authorization":"Bearer another-owner-key"}).status_code == 404
        assert client.get(f"/api/product/v1/analysis-workflows/{workflow_id}").json()["steps"] == workflow["steps"]
        app.state.analysis_workflow_store.update_step(workflow_id,task,owner_id="anonymous",result={**result,"report_version":"older"})
        refreshed = client.get(f"/api/product/v1/analysis-workflows/{workflow_id}").json()
        refreshed_result = next(s["result"] for s in refreshed["steps"] if s["step_id"] == task)
        assert refreshed_result["report_uri"] == result["report_uri"]
        assert refreshed_result["simulated"] is True


def test_demo_validation_and_live_failure_never_substitutes_demo(tmp_path,monkeypatch):
    with TestClient(app_for_demo(tmp_path,monkeypatch)) as client:
        base = {"aoi":AOI,"imagery_item_id":SNAPSHOT["item_id"],"imagery_snapshot":SNAPSHOT,"requested_task_ids":["yield_simple"]}
        assert client.post("/api/product/v1/analysis-workflows",json={**base,"data_mode":"demo"}).status_code == 422
        assert client.post("/api/product/v1/analysis-workflows",json={**base,"data_mode":"demo","demo_crop":"wheat","requested_task_ids":["crop"]}).status_code == 422
        assert client.post("/api/product/v1/analysis-workflows",json={**base,"demo_crop":"wheat"}).status_code == 422
        assert client.post("/api/product/v1/analysis-workflows",json=base).status_code == 502


def test_card_confirmation_persists_demo_and_one_task_reference(tmp_path,monkeypatch):
    app = app_for_demo(tmp_path,monkeypatch)
    with TestClient(app) as client:
        conversation = client.post("/api/product/v1/conversations",json={"title":"演示估产"}).json()["conversation_id"]
        context = {"workspace_id":"demo-workspace","revision":1,"execution_mode":"live","aoi":AOI,
                   "imagery_item_id":SNAPSHOT["item_id"],"imagery_snapshot":SNAPSHOT,"draft_task_ids":["yield_simple"]}
        assert client.put("/api/product/v1/workspaces/demo-workspace/context",json=context).status_code == 200
        body = {"input":{"message":"演示玉米估产","workspace_action":{"action_id":"demo-card","task_ids":["yield_simple"],"yield_demo_crop":"maize"}},"context":{"workspace":context}}
        endpoint = f"/api/product/v1/conversations/{conversation}/submissions"
        response = client.post(endpoint,json=body,headers={"Idempotency-Key":"demo-card"})
        assert response.status_code == 201,response.text
        for _ in range(150):
            submission = client.get(f'/api/product/v1/submissions/{response.json()["submission_id"]}').json()
            if submission["status"] in {"completed","failed"}: break
            time.sleep(.02)
        assert submission["status"] == "completed",submission
        run = client.get(f'/api/product/v1/runs/{submission["run_id"]}').json()
        reference = next(p for p in run["assistant"]["parts"] if p["type"] == "workflow_reference")
        assert reference["data"]["data_mode"] == "demo"
        assert "玉米估产模拟演示" in run["assistant"]["summary"]
        workflow = wait_workflow(client,reference["data"]["workflow_id"])
        assert workflow["demo_crop"] == "maize" and workflow["run_id"] == run["run_id"]
        replay = client.post(endpoint,json=body,headers={"Idempotency-Key":"demo-card"})
        assert replay.json()["submission_id"] == response.json()["submission_id"]
        assert len(client.get("/api/product/v1/workspaces/demo-workspace/workflows").json()) == 1
