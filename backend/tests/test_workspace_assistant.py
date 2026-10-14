"""Map assistant integration: authorization, snapshot freshness and exactly-once tasks."""
import json
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.canonical.router import install_canonical_product_api
from schemas.analysis_workflow import CreateAnalysisWorkflowRequest
from schemas.workspace import WorkspaceContext, WorkspaceIntent
from v2.runtime.store import InMemoryRuntimeStore
from runtime.analysis_workflow_store import AnalysisWorkflowStore

AOI = {"geometry": {"type": "Polygon", "coordinates": [[[100, 38], [100.01, 38], [100.01, 38.01], [100, 38.01], [100, 38]]]}, "source": "drawn"}
SNAPSHOT = {"item_id": "S2-workspace", "collection": "sentinel-2-l2a", "acquired_at": "2026-09-30T00:00:00Z", "selection_token": "valid"}


def test_model_prompt_preserves_enum_values_and_uses_workspace_example():
    from infra.llm.provider import _build_structured_prompt
    prompt = _build_structured_prompt(user_prompt="下一步做什么", response_model=WorkspaceIntent)
    assert '"intent": "advise"' in prompt
    assert 'enum' in prompt and 'configure' in prompt and 'execute' in prompt
    assert 'prosail.simulation' not in prompt


@pytest.mark.parametrize("via_card", [False, True])
def test_apsim_example_mode_reaches_workflow_from_assistant_and_card(tmp_path, monkeypatch, via_card):
    app, launches = make_app(tmp_path, monkeypatch, Planner("execute", tasks=["yield"]))
    with TestClient(app) as client:
        conversation, context = setup(client, apsim_mode="example", draft_task_ids=["yield"])
        action = {"action_id": "example-launch", "task_ids": ["yield"]} if via_card else None
        _, run = submit(client, conversation, context, "根据作物识别运行真实 APSIM 示例", action=action)
        reference = next(part for part in run["assistant"]["parts"] if part["type"] == "workflow_reference")
        item = client.get(f"/api/product/v1/analysis-workflows/{reference['data']['workflow_id']}").json()
        assert item["data_mode"] == "apsim_example"
        assert item["demo_crop"] is None
        assert item["effective_task_ids"] == ["crop", "yield"]
        assert item["steps"][-1]["depends_on"] == ["crop"]
        assert len(launches) == 1


class Provider:
    def get_item(self, item_id):
        return {"id": item_id}

    def validate_selection(self, snapshot, item, geometry):
        from infra.imagery.stac_provider import ImagerySearchError
        if snapshot.selection_token != "valid" or snapshot.item_id != item["id"]:
            raise ImagerySearchError("invalid selection")
        return snapshot


class SearchProvider(Provider):
    def __init__(self, items=None):
        from schemas.spatial import ImageryCandidate
        self.items = items if items is not None else [ImageryCandidate(**SNAPSHOT, cloud_cover=3, coverage_percent=100)]
        self.searches = []
        self.started = threading.Event()
        self.release = threading.Event()
        self.release.set()

    def search(self, request):
        self.searches.append(request)
        self.started.set()
        assert self.release.wait(5)
        return self.items


class Planner:
    def __init__(self, intent="advise", tasks=None, unsupported=None):
        self.intent = intent
        self.tasks = tasks if tasks is not None else ["lai", "crop"]
        self.unsupported = unsupported or []
        self.started = threading.Event()
        self.release = threading.Event()
        self.release.set()
        self.prompts = []

    def generate_structured(self, *, system_prompt, user_prompt, response_model):
        self.prompts.append(json.loads(user_prompt))
        self.started.set()
        assert self.release.wait(5)
        return WorkspaceIntent(intent=self.intent, task_ids=self.tasks, summary="根据当前影像分析。", rationale="共用影像准备。", explicit_execution=self.intent == "execute", unsupported_parameters=self.unsupported)


def make_app(tmp_path, monkeypatch, planner):
    import api.canonical.router as router
    launches = []

    def run_workflow(workflow_id, *, workflows, owner_id, **kwargs):
        launches.append(workflow_id)
        workflows.update_status(workflow_id, owner_id=owner_id, status="completed", detail="测试执行器完成")

    monkeypatch.setattr(router, "run_analysis_workflow", run_workflow)
    app = FastAPI()
    install_canonical_product_api(app, db_path=str(tmp_path / "workspace.sqlite3"), auth_required=False)
    app.state.runtime_store = InMemoryRuntimeStore()
    app.state.runtime_engine = SimpleNamespace(llm_provider=planner)
    app.state.sentinel_stac_provider = Provider()
    return app, launches


def setup(client, **overrides):
    conversation = client.post("/api/product/v1/conversations", json={"title": "workspace"}).json()["conversation_id"]
    context = {"workspace_id": "workspace-1", "revision": 1, "execution_mode": "live", "aoi": AOI, "imagery_item_id": "S2-workspace", "imagery_snapshot": SNAPSHOT, **overrides}
    assert client.put("/api/product/v1/workspaces/workspace-1/context", json=context).status_code == 200
    return conversation, context


def submit(client, conversation, context, message="下一步做什么", action=None, key=None, ui=None):
    response = client.post(f"/api/product/v1/conversations/{conversation}/submissions", json={"input": {"message": message, "workspace_action": action}, "context": {"workspace": context, "workspace_ui": ui}}, headers={"Idempotency-Key": key} if key else {})
    assert response.status_code == 201, response.text
    submission_id = response.json()["submission_id"]
    for _ in range(150):
        sub = client.get(f"/api/product/v1/submissions/{submission_id}").json()
        if sub["status"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(0.02)
    else:
        raise AssertionError("assistant did not finish")
    run = client.get(f"/api/product/v1/runs/{sub['run_id']}").json()
    return response.json(), run


def test_advice_contains_cards_and_current_map_without_starting(tmp_path, monkeypatch):
    planner = Planner()
    app, launches = make_app(tmp_path, monkeypatch, planner)
    with TestClient(app) as client:
        conversation, context = setup(client)
        _, run = submit(client, conversation, context)
        assert run["status"] == "completed"
        assert [p["type"] for p in run["assistant"]["parts"]] == ["analysis_plan", "parameter_set", "action_card"]
        assert planner.prompts[0]["workspace"]["aoi"]["geometry"] == AOI["geometry"]
        assert "selection_token" not in planner.prompts[0]["workspace"]["imagery_snapshot"]
        assert launches == []


def test_explicit_instruction_starts_one_workflow_and_survives_event_replay(tmp_path, monkeypatch):
    app, launches = make_app(tmp_path, monkeypatch, Planner("execute"))
    with TestClient(app) as client:
        conversation, context = setup(client)
        first, run = submit(client, conversation, context, "执行LAI和作物识别", key="request-1")
        replay, replay_run = submit(client, conversation, context, "执行LAI和作物识别", key="request-1")
        assert first == replay
        assert run == replay_run
        reference = run["assistant"]["parts"][-1]
        workflow = client.get(f"/api/product/v1/analysis-workflows/{reference['data']['workflow_id']}").json()
        assert workflow["requested_task_ids"] == ["lai", "crop"]
        assert workflow["conversation_id"] == conversation
        assert workflow["parameters"]["target_resolution_m"] == 20
        assert workflow["lai_query"] == "执行LAI和作物识别"
        assert launches == [workflow["workflow_id"]]
        events = client.get(f"/api/product/v1/submissions/{first['submission_id']}/events").text
        assert "assistant.part.updated" in events and "workflow.linked" in events


def test_simplified_yield_uses_shared_execution_and_keeps_apsim_separate(tmp_path, monkeypatch):
    app, launches = make_app(tmp_path, monkeypatch, Planner('execute', tasks=['yield_simple']))
    with TestClient(app) as client:
        conversation, context = setup(client)
        first, run = submit(client, conversation, context, '执行小麦估产', key='simple-request')
        replay, _ = submit(client, conversation, context, '执行小麦估产', key='simple-request')
        assert first == replay
        reference = run['assistant']['parts'][-1]['data']
        workflow = client.get(f"/api/product/v1/analysis-workflows/{reference['workflow_id']}").json()
        assert workflow['requested_task_ids'] == ['yield_simple']
        assert workflow['effective_task_ids'] == ['crop', 'yield_simple']
        assert workflow['yield_inputs']['sowing_date'] is None
        assert launches == [workflow['workflow_id']]


@pytest.mark.parametrize("overrides,missing", [({"aoi": None}, "绘制"), ({"imagery_item_id": None, "imagery_snapshot": None}, "影像"), ({"execution_mode": "demo"}, "演示")])
def test_missing_inputs_or_demo_never_start_real_task(tmp_path, monkeypatch, overrides, missing):
    app, launches = make_app(tmp_path, monkeypatch, Planner("execute"))
    with TestClient(app) as client:
        conversation, context = setup(client, **overrides)
        _, run = submit(client, conversation, context, "执行任务")
        assert missing in run["assistant"]["summary"]
        assert launches == []


def test_context_changed_while_model_plans_invalidates_execution(tmp_path, monkeypatch):
    planner = Planner("execute")
    planner.release.clear()
    app, launches = make_app(tmp_path, monkeypatch, planner)
    with TestClient(app) as client:
        conversation, context = setup(client)
        response = client.post(f"/api/product/v1/conversations/{conversation}/submissions", json={"input": {"message": "执行LAI"}, "context": {"workspace": context}})
        assert planner.started.wait(3)
        assert client.put("/api/product/v1/workspaces/workspace-1/context", json={**context, "revision": 2, "imagery_item_id": None, "imagery_snapshot": None}).status_code == 200
        planner.release.set()
        for _ in range(100):
            result = client.get(f"/api/product/v1/submissions/{response.json()['submission_id']}").json()
            if result["status"] == "failed":
                break
            time.sleep(0.02)
        assert result["status"] == "failed"
        assert launches == []


def test_card_executes_same_service_and_rejects_stale_or_forged_actions(tmp_path, monkeypatch):
    app, launches = make_app(tmp_path, monkeypatch, Planner())
    with TestClient(app) as client:
        conversation, context = setup(client)
        _, advice = submit(client, conversation, context)
        action_id = advice["assistant"]["parts"][-1]["data"]["action_id"]
        action = {"action_id": action_id, "source_run_id": advice["run_id"], "task_ids": ["growth"]}
        _, executed = submit(client, conversation, context, "执行长势", action=action)
        assert executed["status"] == "completed"
        workflow_id = executed["assistant"]["parts"][-1]["data"]["workflow_id"]
        workflow = client.get(f"/api/product/v1/analysis-workflows/{workflow_id}").json()
        assert workflow["effective_task_ids"] == ["lai", "growth"]
        assert launches == [workflow_id]
        _, forged = submit(client, conversation, context, action={**action, "action_id": "forged"})
        assert forged["status"] == "failed"
        changed = {**context, "revision": 2, "farm_id": "other-farm"}
        client.put("/api/product/v1/workspaces/workspace-1/context", json=changed)
        _, stale = submit(client, conversation, changed, action=action)
        assert stale["status"] == "failed"
        assert len(launches) == 1


def test_unsupported_parameter_change_does_not_execute(tmp_path, monkeypatch):
    app, launches = make_app(tmp_path, monkeypatch, Planner("execute", unsupported=["分辨率10m"]))
    with TestClient(app) as client:
        conversation, context = setup(client)
        _, run = submit(client, conversation, context, "改为10m并执行LAI")
        assert "不支持修改" in run["assistant"]["summary"]
        assert launches == []


@pytest.mark.parametrize("via_card", [False, True])
def test_lai_launch_keeps_current_draft_description_for_automatic_parameters(tmp_path, monkeypatch, via_card):
    planner = Planner("configure", tasks=["lai"])
    app, launches = make_app(tmp_path, monkeypatch, planner)
    with TestClient(app) as client:
        conversation, context = setup(client, draft_task_ids=["lai"])
        _, draft = submit(client, conversation, context, "这是山东小麦田，请自动配置LAI参数")
        parameters = next(p for p in draft["assistant"]["parts"] if p["type"] == "parameter_set")
        assert any(p["name"] == "LAI 场景参数" for p in parameters["data"]["parameters"])
        assert launches == []
        planner.intent = "execute"
        action = {"action_id": "lai-auto-launch", "task_ids": ["lai"]} if via_card else None
        _, run = submit(client, conversation, context, "开始执行", action=action)
        reference = next(p for p in run["assistant"]["parts"] if p["type"] == "workflow_reference")
        workflow = client.get(f"/api/product/v1/analysis-workflows/{reference['data']['workflow_id']}").json()
        assert "山东小麦田" in workflow["lai_query"]
        assert "开始执行" in workflow["lai_query"]
        assert len(launches) == 1


def test_durable_action_replay_and_revision_checks_are_transactional(tmp_path):
    db = tmp_path / "actions.sqlite3"
    store = AnalysisWorkflowStore(str(db))
    context = WorkspaceContext(workspace_id="ws", revision=1, aoi=AOI, imagery_item_id="S2-workspace", imagery_snapshot=SNAPSHOT)
    store.sync_workspace(context, owner_id="owner")
    body = CreateAnalysisWorkflowRequest(aoi=AOI, imagery_item_id="S2-workspace", imagery_snapshot=SNAPSHOT, requested_task_ids=["lai"], action_id="same-action", start_immediately=False)
    first = store.create(body, owner_id="owner", workspace=context)
    store.close()
    restored = AnalysisWorkflowStore(str(db))
    assert restored.create(body, owner_id="owner", workspace=context).workflow_id == first.workflow_id
    assert restored.claim_start(first.workflow_id, owner_id="owner")
    assert not restored.claim_start(first.workflow_id, owner_id="owner")
    with pytest.raises(ValueError):
        restored.create(body.model_copy(update={"requested_task_ids": ["crop"]}), owner_id="owner", workspace=context)
    with pytest.raises(ValueError):
        restored.check_workspace(context, owner_id="another")
    restored.sync_workspace(context.model_copy(update={"revision": 2}), owner_id="owner")
    with pytest.raises(ValueError):
        restored.sync_workspace(context, owner_id="owner")
    restored.close()


def test_cancelled_planning_cannot_start_workflow(tmp_path, monkeypatch):
    planner = Planner("execute")
    planner.release.clear()
    app, launches = make_app(tmp_path, monkeypatch, planner)
    with TestClient(app) as client:
        conversation, context = setup(client)
        response = client.post(f"/api/product/v1/conversations/{conversation}/submissions", json={"input": {"message": "执行LAI"}, "context": {"workspace": context}})
        assert planner.started.wait(3)
        cancelled = client.post(f"/api/product/v1/submissions/{response.json()['submission_id']}/cancel")
        assert cancelled.status_code == 200
        planner.release.set()
        time.sleep(0.1)
        assert launches == []


def test_planner_receives_original_workflow_cards_and_historical_plan(tmp_path, monkeypatch):
    planner = Planner("configure", tasks=["lai"])
    app, launches = make_app(tmp_path, monkeypatch, planner)
    with TestClient(app) as client:
        conversation, context = setup(client, imagery_item_id=None, imagery_snapshot=None)
        _, configured = submit(client, conversation, context, "我要对这块地做LAI反演")
        selected = {**context, "revision": 2, "imagery_item_id": "S2-workspace", "imagery_snapshot": SNAPSHOT, "draft_task_ids": ["lai"]}
        client.put("/api/product/v1/workspaces/workspace-1/context", json=selected)
        ui = {"stage": "ready", "imagery_candidates": [{"item_id": "S2-workspace", "observed_at": "2026-09-30", "cloud": "0%", "recommended": True, "selected": True}], "cards": [
            {"card_id": "imagery-selection", "kind": "imagery_selected", "title": "影像已选定", "selected_candidate_id": "S2-workspace"},
            {"card_id": "professional-tasks", "kind": "task_selection", "title": "选择专业任务", "task_ids": ["lai"], "fields": {"影像准备分辨率": "20 m（固定）"}},
        ]}
        submit(client, conversation, selected, "我现在选的是哪景影像、什么任务？", ui=ui)
        prompt = planner.prompts[-1]
        assert prompt["workspace"]["imagery_item_id"] == "S2-workspace"
        assert prompt["workspace_ui"]["cards"][1]["task_ids"] == ["lai"]
        assert prompt["workspace_ui"]["imagery_candidates"][0]["selected"]
        previous = next(plan for plan in prompt["recent_plans"] if plan["run_id"] == configured["run_id"])
        assert previous["same_area"] and not previous["current_imagery"]
        assert previous["parts"][0]["data"]["requested_task_ids"] == ["lai"]
        assert launches == []


def test_late_configuration_follows_selected_image_without_executing(tmp_path, monkeypatch):
    planner = Planner("configure", tasks=["lai"])
    planner.release.clear()
    app, launches = make_app(tmp_path, monkeypatch, planner)
    with TestClient(app) as client:
        conversation, context = setup(client, imagery_item_id=None, imagery_snapshot=None)
        response = client.post(f"/api/product/v1/conversations/{conversation}/submissions", json={"input": {"message": "我要这块地做LAI反演"}, "context": {"workspace": context}})
        assert planner.started.wait(3)
        selected = {**context, "revision": 2, "imagery_item_id": "S2-workspace", "imagery_snapshot": SNAPSHOT}
        assert client.put("/api/product/v1/workspaces/workspace-1/context", json=selected).status_code == 200
        planner.release.set()
        for _ in range(100):
            result = client.get(f"/api/product/v1/submissions/{response.json()['submission_id']}").json()
            if result["status"] in {"completed", "failed"}:
                break
            time.sleep(0.02)
        assert result["status"] == "completed"
        run = client.get(f"/api/product/v1/runs/{result['run_id']}").json()
        plan = run["assistant"]["parts"][0]["data"]
        assert plan["imagery_item_id"] == "S2-workspace" and plan["revision"] == 2
        assert plan["requested_task_ids"] == ["lai"] and plan["missing_inputs"] == []
        assert launches == []


def test_late_configuration_does_not_override_manual_task_choices(tmp_path, monkeypatch):
    planner = Planner("configure", tasks=["lai"])
    planner.release.clear()
    app, launches = make_app(tmp_path, monkeypatch, planner)
    with TestClient(app) as client:
        conversation, context = setup(client)
        response = client.post(f"/api/product/v1/conversations/{conversation}/submissions", json={"input": {"message": "只做LAI"}, "context": {"workspace": context}})
        assert planner.started.wait(3)
        client.put("/api/product/v1/workspaces/workspace-1/context", json={**context, "revision": 2, "draft_task_ids": ["crop"]})
        planner.release.set()
        for _ in range(100):
            result = client.get(f"/api/product/v1/submissions/{response.json()['submission_id']}").json()
            if result["status"] == "failed":
                break
            time.sleep(0.02)
        assert result["status"] == "failed"
        assert app.state.analysis_workflow_store.get_workspace("workspace-1", owner_id="anonymous").draft_task_ids == ["crop"]
        assert launches == []


def test_active_card_confirms_current_draft_without_model_or_old_plan(tmp_path, monkeypatch):
    planner = Planner("advise", tasks=["crop"])
    app, launches = make_app(tmp_path, monkeypatch, planner)
    with TestClient(app) as client:
        conversation, context = setup(client, draft_task_ids=["growth"])
        action = {"action_id": "current-card-launch", "task_ids": ["growth"]}
        first, run = submit(client, conversation, context, "执行长势", action=action, key="current-card-launch")
        replay, _ = submit(client, conversation, context, "执行长势", action=action, key="current-card-launch")
        assert first == replay and planner.prompts == []
        workflow_id = run["assistant"]["parts"][-1]["data"]["workflow_id"]
        workflow = client.get(f"/api/product/v1/analysis-workflows/{workflow_id}").json()
        assert workflow["requested_task_ids"] == ["growth"]
        assert workflow["effective_task_ids"] == ["lai", "growth"]
        assert launches == [workflow_id]
        _, mismatched = submit(client, conversation, context, action={"action_id": "changed-task", "task_ids": ["crop"]})
        assert mismatched["status"] == "failed" and len(launches) == 1


@pytest.mark.parametrize("intent", ["status", "explain"])
def test_read_only_questions_do_not_create_configuration_cards(tmp_path, monkeypatch, intent):
    app, launches = make_app(tmp_path, monkeypatch, Planner(intent))
    with TestClient(app) as client:
        conversation, context = setup(client, draft_task_ids=["lai"])
        _, run = submit(client, conversation, context, "解释当前参数")
        assert run["status"] == "completed"
        assert not any(part["type"] in {"action_card", "analysis_plan", "parameter_set"} for part in run["assistant"]["parts"])
        assert launches == []


def test_clearing_tasks_gives_no_execution_instruction(tmp_path, monkeypatch):
    app, launches = make_app(tmp_path, monkeypatch, Planner("configure", tasks=[]))
    with TestClient(app) as client:
        conversation, context = setup(client, draft_task_ids=["lai"])
        _, run = submit(client, conversation, context, "清空任务")
        assert "已清空" in run["assistant"]["summary"]
        assert run["assistant"]["parts"][0]["data"]["requested_task_ids"] == []
        assert launches == []


def test_competing_workspace_launches_register_only_one_task(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    db = str(tmp_path / "competing.sqlite3")
    first, second = AnalysisWorkflowStore(db), AnalysisWorkflowStore(db)
    context = WorkspaceContext(workspace_id="ws", revision=1, aoi=AOI, imagery_item_id="S2-workspace", imagery_snapshot=SNAPSHOT, draft_task_ids=["lai"])
    first.sync_workspace(context, owner_id="owner")
    body = CreateAnalysisWorkflowRequest(aoi=AOI, imagery_item_id="S2-workspace", imagery_snapshot=SNAPSHOT, requested_task_ids=["lai"], workspace_id="ws", workspace_revision=1, start_immediately=False)
    gate = threading.Barrier(2)

    def launch(store, action):
        gate.wait()
        try:
            return store.create(body.model_copy(update={"action_id": action}), owner_id="owner", workspace=context).workflow_id
        except ValueError:
            return None

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(launch, first, "button"), pool.submit(launch, second, "chat")]
        results = [future.result() for future in futures]
    assert sum(result is not None for result in results) == 1
    assert len(first.list_for_workspace("ws", owner_id="owner")) == 1
    first.close()
    second.close()


def test_automatic_search_selects_and_executes_multiple_tasks_once(tmp_path, monkeypatch):
    from datetime import date
    monkeypatch.setattr("runtime.workspace_assistant.imagery_today", lambda: date(2026, 10, 14))
    from schemas.spatial import ImageryCandidate
    app, launches = make_app(tmp_path, monkeypatch, Planner("execute", tasks=["crop", "growth"]))
    provider = SearchProvider([
        ImageryCandidate(**{**SNAPSHOT, "item_id": "cloudy"}, cloud_cover=15, coverage_percent=100),
        ImageryCandidate(**SNAPSHOT, cloud_cover=3, coverage_percent=100),
    ])
    app.state.sentinel_stac_provider = provider
    with TestClient(app) as client:
        conversation, context = setup(client, auto_execute=True, imagery_item_id=None, imagery_snapshot=None,
                                      imagery_search={"start_date": "2026-10-14", "end_date": "2026-10-14"})
        first, run = submit(client, conversation, context, "帮我识别作物并分析长势", key="auto-1")
        replay, replay_run = submit(client, conversation, context, "帮我识别作物并分析长势", key="auto-1")
        assert first == replay and run == replay_run
        assert run["status"] == "completed", run
        ref = run["assistant"]["parts"][-1]["data"]
        assert ref["auto_execute"] is True
        workflow = client.get(f"/api/product/v1/analysis-workflows/{ref['workflow_id']}").json()
        assert workflow["imagery_item_id"] == "S2-workspace"
        assert workflow["requested_task_ids"] == ["crop", "growth"]
        assert set(workflow["effective_task_ids"]) == {"crop", "lai", "growth"}
        assert len(launches) == len(provider.searches) == 1
        assert provider.searches[0].start_date == "2026-07-16"
        assert provider.searches[0].end_date == "2026-10-14"
        assert "已自动选择" in run["assistant"]["summary"]
        assert "完成后" in run["assistant"]["summary"]
        # Automatic selection never overwrites a user-editable workspace.
        saved = app.state.analysis_workflow_store.get_workspace("workspace-1", owner_id="anonymous")
        assert saved.imagery_item_id is None
        events = client.get(f"/api/product/v1/submissions/{first['submission_id']}/events").text
        payloads = [json.loads(line[6:]) for line in events.splitlines() if line.startswith("data: ")]
        assert any("自动执行：正在搜索" in item.get("detail", "") for item in payloads)


@pytest.mark.parametrize("intent,auto,overrides", [
    ("execute", False, {}), ("advise", True, {}), ("configure", True, {}),
    ("status", True, {}), ("explain", True, {}), ("execute", True, {"aoi": None}),
    ("execute", True, {"execution_mode": "demo"}),
])
def test_auto_permission_does_not_authorize_unrelated_actions(tmp_path, monkeypatch, intent, auto, overrides):
    app, launches = make_app(tmp_path, monkeypatch, Planner(intent))
    provider = SearchProvider()
    app.state.sentinel_stac_provider = provider
    with TestClient(app) as client:
        conversation, context = setup(client, auto_execute=auto, imagery_item_id=None, imagery_snapshot=None, **overrides)
        _, run = submit(client, conversation, context)
        assert run["status"] == "completed"
        assert launches == provider.searches == []


def test_automatic_request_reuses_verified_selection(tmp_path, monkeypatch):
    app, launches = make_app(tmp_path, monkeypatch, Planner("execute"))
    provider = SearchProvider()
    app.state.sentinel_stac_provider = provider
    with TestClient(app) as client:
        conversation, context = setup(client, auto_execute=True)
        _, run = submit(client, conversation, context, "帮我分析")
        assert run["status"] == "completed"
        assert len(launches) == 1 and not provider.searches


@pytest.mark.parametrize("change", ["revoke", "aoi", "cancel"])
def test_changes_during_automatic_search_prevent_launch(tmp_path, monkeypatch, change):
    app, launches = make_app(tmp_path, monkeypatch, Planner("execute"))
    provider = SearchProvider()
    provider.release.clear()
    app.state.sentinel_stac_provider = provider
    with TestClient(app) as client:
        conversation, context = setup(client, auto_execute=True, imagery_item_id=None, imagery_snapshot=None,
                                      imagery_search={"end_date": "2026-10-14"})
        response = client.post(f"/api/product/v1/conversations/{conversation}/submissions", json={"input": {"message": "分析长势"}, "context": {"workspace": context}})
        assert provider.started.wait(3)
        submission_id = response.json()["submission_id"]
        if change == "cancel":
            assert client.post(f"/api/product/v1/submissions/{submission_id}/cancel").status_code == 200
        else:
            updates = {"auto_execute": False} if change == "revoke" else {"aoi": None}
            assert client.put("/api/product/v1/workspaces/workspace-1/context", json={**context, "revision": 2, **updates}).status_code == 200
        provider.release.set()
        for _ in range(150):
            current = client.get(f"/api/product/v1/submissions/{submission_id}").json()
            if current["status"] in {"failed", "cancelled"}:
                break
            time.sleep(0.02)
        assert current["status"] in {"failed", "cancelled"}
        assert launches == []


@pytest.mark.parametrize("items", [[], [{**SNAPSHOT, "cloud_cover": 99}], [{**SNAPSHOT, "cloud_cover": 0, "coverage_percent": 50}], [{**SNAPSHOT, "cloud_cover": 0, "selection_token": None}]])
def test_no_suitable_automatic_imagery_never_starts(tmp_path, monkeypatch, items):
    from schemas.spatial import ImageryCandidate
    app, launches = make_app(tmp_path, monkeypatch, Planner("execute"))
    app.state.sentinel_stac_provider = SearchProvider([ImageryCandidate(**item) for item in items])
    with TestClient(app) as client:
        conversation, context = setup(client, auto_execute=True, imagery_item_id=None, imagery_snapshot=None,
                                      imagery_search={"end_date": "2026-10-14"})
        _, run = submit(client, conversation, context)
        assert run["status"] == "failed"
        assert "未找到符合" in run["assistant"]["summary"]
        assert not launches


def test_explicit_imagery_window_overrides_existing_selection(tmp_path, monkeypatch):
    from schemas.spatial import ImageryCandidate
    from schemas.workspace import WorkspaceImagerySearch
    planner = Planner("execute", tasks=["lai"])
    original = planner.generate_structured

    def plan(**kwargs):
        return original(**kwargs).model_copy(update={"imagery_search": WorkspaceImagerySearch(start_date="2026-06-01", end_date="2026-06-30", max_cloud_cover=10)})

    planner.generate_structured = plan
    app, launches = make_app(tmp_path, monkeypatch, planner)
    provider = SearchProvider([
        ImageryCandidate(**SNAPSHOT, cloud_cover=0),
        ImageryCandidate(**{**SNAPSHOT, "item_id": "summer", "acquired_at": "2026-06-15T00:00:00Z"}, cloud_cover=5),
    ])
    app.state.sentinel_stac_provider = provider
    with TestClient(app) as client:
        conversation, context = setup(client, auto_execute=True)
        _, run = submit(client, conversation, context, "分析六月的LAI")
        assert run["status"] == "completed"
        workflow = client.get(f"/api/product/v1/analysis-workflows/{launches[0]}").json()
        assert workflow["imagery_item_id"] == "summer"
        assert provider.searches[0].max_cloud_cover == 10


def test_partial_automatic_filter_preserves_workspace_dates():
    from runtime.workspace_assistant import automatic_imagery_request
    from schemas.workspace import WorkspaceImagerySearch
    context = WorkspaceContext(workspace_id="ws", revision=1, aoi=AOI,
                               imagery_search={"start_date": "2026-06-01", "end_date": "2026-06-30"})
    intent = WorkspaceIntent(intent="execute", summary="分析", imagery_search=WorkspaceImagerySearch(max_cloud_cover=5))
    search = automatic_imagery_request(context, intent)
    assert (search.start_date, search.end_date, search.max_cloud_cover) == ("2026-06-01", "2026-06-30", 5)
