"""Professional mode pauses real tools and executes the exact confirmed values."""
from types import SimpleNamespace
import threading

import pytest
from fastapi.testclient import TestClient

from runtime.analysis_workflow_store import AnalysisWorkflowStore
from schemas.runtime import SceneParameters
from schemas.workspace import WorkspaceContext, WorkspaceIntent
from v2.runtime.store import InMemoryRuntimeStore
from test_workspace_assistant import make_app, Planner, SearchProvider, setup, submit
from test_workspace_lai import setup_app, SceneProvider
from test_analysis_workflow_api import SNAPSHOT, _wait_for_terminal


def decision(client, review, context, **values):
    return client.post(f"/api/product/v1/professional-reviews/{review['review_id']}/decision",
                       json={"context": context, **values}, headers={"Idempotency-Key": "review-" + review["review_id"]})


def proposal(run):
    return next(p["data"]["review"] for p in run["assistant"]["parts"] if p["type"] == "professional_review")


def test_professional_search_and_workflow_wait_for_each_confirmation(tmp_path, monkeypatch):
    app, launches = make_app(tmp_path, monkeypatch, Planner("execute"))
    provider = SearchProvider()
    app.state.sentinel_stac_provider = provider
    with TestClient(app) as client:
        conv, ctx = setup(client, professional_mode=True, imagery_item_id=None, imagery_snapshot=None,
                          imagery_search={"start_date": "2026-01-01", "end_date": "2026-10-14"})
        _, run = submit(client, conv, ctx, "分析长势")
        review = proposal(run)
        assert review["phase"] == "search" and run["status"] == "completed"
        assert not provider.searches and not launches
        edited = {"start_date": "2026-09-01", "end_date": "2026-09-30", "max_cloud_cover": 5}
        response = decision(client, review, ctx, search=edited)
        assert response.status_code == 200, response.text
        replay = decision(client, review, ctx, search=edited)
        assert replay.json() == response.json()
        next_review = response.json()["next_review"]
        assert next_review["phase"] == "workflow"
        assert (provider.searches[0].start_date, provider.searches[0].max_cloud_cover) == ("2026-09-01", 5)
        assert len(provider.searches) == 1 and not launches
        started = decision(client, next_review, ctx, imagery_item_id="S2-workspace", task_ids=["growth", "crop"])
        assert started.status_code == 200, started.text
        flow = started.json()["workflow"]
        assert flow["professional_mode"] is True
        assert flow["requested_task_ids"] == ["growth", "crop"]
        assert set(flow["effective_task_ids"]) == {"crop", "lai", "growth"}
        assert len(launches) == 1
        assert decision(client, next_review, ctx, imagery_item_id="S2-workspace", task_ids=["growth", "crop"]).json() == started.json()
        assert len(launches) == 1


@pytest.mark.parametrize("change", [{"professional_mode": False}, {"imagery_item_id": None, "imagery_snapshot": None}, {"aoi": None}, {"draft_task_ids": ["crop"]}])
def test_stale_professional_card_cannot_execute(tmp_path, monkeypatch, change):
    app, launches = make_app(tmp_path, monkeypatch, Planner("execute"))
    with TestClient(app) as client:
        conv, ctx = setup(client, professional_mode=True)
        _, run = submit(client, conv, ctx)
        review = proposal(run)
        updated = {**ctx, **change, "revision": 2}
        assert client.put("/api/product/v1/workspaces/workspace-1/context", json=updated).status_code == 200
        assert decision(client, review, updated).status_code == 409
        assert not launches


def test_professional_cancellation_is_durable_and_performs_no_tool(tmp_path, monkeypatch):
    app, launches = make_app(tmp_path, monkeypatch, Planner("execute"))
    with TestClient(app) as client:
        conv, ctx = setup(client, professional_mode=True)
        _, run = submit(client, conv, ctx)
        review = proposal(run)
        cancelled = decision(client, review, ctx, decision="cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["review"]["status"] == "cancelled"
        assert not launches
    reopened = AnalysisWorkflowStore(str(tmp_path / "workspace.sqlite3"))
    assert reopened.get_review(review["review_id"], owner_id="anonymous").status == "cancelled"
    assert reopened.get_review(review["review_id"], owner_id="other") is None
    reopened.close()


@pytest.mark.parametrize("intent", ["advise", "configure", "explain", "status"])
def test_professional_consultation_does_not_create_execution_review(tmp_path, monkeypatch, intent):
    app, launches = make_app(tmp_path, monkeypatch, Planner(intent))
    with TestClient(app) as client:
        conv, ctx = setup(client, professional_mode=True)
        _, run = submit(client, conv, ctx)
        assert not any(p["type"] == "professional_review" for p in run["assistant"]["parts"])
        assert not launches


class ProfessionalProvider(SceneProvider):
    def generate_structured(self, *, response_model, **kwargs):
        if response_model is WorkspaceIntent:
            return WorkspaceIntent(intent="execute", task_ids=["crop", "lai"], summary="分析作物和LAI", rationale="共用影像")
        return super().generate_structured(response_model=response_model, **kwargs)


def test_real_lai_pauses_after_crop_and_uses_edited_confirmed_range(tmp_path, monkeypatch):
    import runtime.analysis_workflow_runner as runner
    provider = ProfessionalProvider()
    app = setup_app(tmp_path, monkeypatch, provider)
    app.state.runtime_store = InMemoryRuntimeStore()
    calls = []
    real_report = runner.run_lai_html_report

    def report(**kwargs):
        calls.append(kwargs)
        return real_report(**kwargs)

    monkeypatch.setattr(runner, "run_lai_html_report", report)
    with TestClient(app) as client:
        conv, ctx = setup(client, professional_mode=True, imagery_item_id=SNAPSHOT["item_id"], imagery_snapshot=SNAPSHOT)
        _, run = submit(client, conv, ctx, "按识别作物配置LAI")
        started = decision(client, proposal(run), ctx)
        assert started.status_code == 200, started.text
        workflow_id = started.json()["workflow"]["workflow_id"]
        paused = _wait_for_terminal(client, workflow_id)
        assert paused["status"] == "blocked"
        assert next(s for s in paused["steps"] if s["step_id"] == "crop")["status"] == "completed"
        lai_step = next(s for s in paused["steps"] if s["step_id"] == "lai")
        assert lai_step["status"] == "blocked" and lai_step["analysis_id"] is None and not calls
        assert provider.prompts == []
        # The crop judgement falls back to the model result when the model cannot answer.
        crop_step = next(s for s in paused["steps"] if s["step_id"] == "crop")["result"]
        assert crop_step["crop_decision"]["source"] == "model_fallback"
        assert crop_step["crop_decision"]["final_name_zh"] == "玉米"
        reviews = client.get("/api/product/v1/workspaces/workspace-1/professional-reviews").json()
        crop_review = next(review for review in reviews if review["phase"] == "crop" and review["status"] == "pending")
        assert crop_review["proposed_crop"]["final_class_id"] == 0
        # Retry cannot bypass a pending professional gate.
        assert client.post(f"/api/product/v1/analysis-workflows/{workflow_id}/retry", json={"step_id": "lai"}).status_code == 409
        ctx = {**ctx, "revision": 2, "active_workflow_id": workflow_id, "draft_task_ids": ["crop", "lai"]}
        assert client.put("/api/product/v1/workspaces/workspace-1/context", json=ctx).status_code == 200
        confirmed_crop = decision(client, crop_review, ctx, crop_class_id=0)
        assert confirmed_crop.status_code == 200, confirmed_crop.text
        assert decision(client, crop_review, ctx, crop_class_id=0).json() == confirmed_crop.json()
        after_crop = _wait_for_terminal(client, workflow_id)
        assert after_crop["status"] == "blocked"
        reviews = client.get("/api/product/v1/workspaces/workspace-1/professional-reviews").json()
        pending = next(review for review in reviews if review["phase"] == "lai" and review["status"] == "pending")
        assert pending["proposed_scene"]["lai_range"] == [4, 5]
        assert pending["proposed_scene"]["context"]["crop_prediction"]["name_zh"] == "玉米"
        assert pending["proposed_scene"]["context"]["crop_decision"]["final_name_zh"] == "玉米"
        assert len(provider.prompts) == 1
        invalid = {"lai_range": [9, 10], "cab_range": None, "lidfa_range": None, "psoil_range": None}
        rejected = decision(client, pending, ctx, scene=invalid)
        assert rejected.status_code == 400 and "不足" in rejected.text
        assert not calls
        assert app.state.analysis_workflow_store.get_review(pending["review_id"], owner_id="anonymous").status == "pending"
        edited = {**invalid, "lai_range": [0, 2]}
        response = decision(client, pending, ctx, scene=edited)
        assert response.status_code == 200, response.text
        assert decision(client, pending, ctx, scene=edited).json() == response.json()
        completed = _wait_for_terminal(client, workflow_id)
        assert completed["status"] == "completed", completed
        result = next(s for s in completed["steps"] if s["step_id"] == "lai")["result"]
        assert len(calls) == len(provider.prompts) == 1
        assert calls[0]["scene_constraints"] == {"lai_range": [0, 2]}
        assert calls[0]["strict_scene_constraints"] is True
        assert result["lai_mean"] == 1
        assert result["scene_parameters"]["source"] == "user_confirmed"
        assert result["scene_parameters"]["recommendation"]["lai_range"] == [4, 5]
        assert result["constraint_application"]["requested"] == {"lai_range": [0, 2]}
        assert result["constraint_application"]["effective"] == {"lai_range": [0, 2]}
        persisted = client.get(result["report_data_uri"]).json()
        assert persisted["result"]["scene_parameters"]["lai_range"] == [0, 2]


def test_professional_and_automatic_cannot_be_enabled_together():
    with pytest.raises(ValueError, match="不能同时"):
        WorkspaceContext(workspace_id="ws", revision=1, professional_mode=True, auto_execute=True)


def test_concurrent_review_consumers_claim_only_once(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    app, _ = make_app(tmp_path, monkeypatch, Planner("execute"))
    with TestClient(app) as client:
        conv, ctx = setup(client, professional_mode=True)
        _, run = submit(client, conv, ctx)
        review = proposal(run)
    first = AnalysisWorkflowStore(str(tmp_path / "workspace.sqlite3"))
    second = AnalysisWorkflowStore(str(tmp_path / "workspace.sqlite3"))
    gate = threading.Barrier(2)

    def claim(store):
        gate.wait()
        try:
            store.claim_review(review["review_id"], WorkspaceContext.model_validate(ctx), owner_id="anonymous", parameters={})
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(claim, first), pool.submit(claim, second)]
        assert sum(f.result() for f in futures) == 1
    second.close()
    first.close()
