from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.canonical.router import install_canonical_product_api
from schemas.runtime import AgentStepV2, RequestContextV2, ResolvedDatasetV2, RunDetail
from v2.agents.registry import build_default_agent_registry
from v2.packs.registry import build_default_pack_registry
from v2.policies.registry import build_default_policy_registry
from v2.runtime.engine import BoundedRuntimeEngine
from v2.runtime.planner import ChatFirstPlanner
from v2.runtime.store import InMemoryRuntimeStore
from v2.tools.registry import ToolRegistryV2


class _CapturingPlanner:
    def __init__(self) -> None:
        self.message: str | None = None
        self.context: RequestContextV2 | None = None

    def plan(self, *, message: str, request_context: RequestContextV2, **_kwargs) -> AgentStepV2:
        self.message = message
        self.context = request_context
        return AgentStepV2(action="reply", reasoning="test", response_message="accepted")


def test_dataset_reference_stays_structured_and_preserves_user_message(tmp_path) -> None:
    store = InMemoryRuntimeStore()
    engine = BoundedRuntimeEngine(
        store=store,
        tool_registry=ToolRegistryV2(definitions={}),
        policy_registry=build_default_policy_registry(),
        agent_registry=build_default_agent_registry(),
        pack_registry=build_default_pack_registry(),
    )
    planner = _CapturingPlanner()
    engine._planner = planner
    app = FastAPI()
    app.state.runtime_store = store
    app.state.runtime_engine = engine
    install_canonical_product_api(app, db_path=str(tmp_path / "product.sqlite3"))
    source = tmp_path / "maize-scene.tif"
    source.write_bytes(b"scene")
    original_message = "请使用这个数据集分析玉米 LAI。"

    with TestClient(app) as client:
        conversation = client.post("/api/product/v1/conversations", json={"title": "dataset context"})
        dataset = client.post("/api/product/v1/datasets", json={
            "source": {"kind": "local_path", "uri": str(source)},
            "display_name": "maize-scene.tif",
            "defaults": {"region": "gansu", "crop_type": "maize", "task_type": "lai_inversion"},
            "metadata": {"content_type": "image/tiff"},
        })
        submission = client.post(
            f"/api/product/v1/conversations/{conversation.json()['conversation_id']}/submissions",
            json={"input": {"message": original_message, "refs": [{"type": "dataset", "id": dataset.json()["dataset_id"]}]}},
        )
        assert submission.status_code == 201
        submission_id = submission.json()["submission_id"]
        for _ in range(100):
            state = client.get(f"/api/product/v1/submissions/{submission_id}").json()
            if state["status"] in {"completed", "failed"}:
                break
            time.sleep(0.01)
        else:
            raise AssertionError("submission did not become terminal")

    assert state["status"] == "completed"
    assert planner.message == original_message
    assert "[dataset:" not in planner.message
    assert planner.context is not None
    assert planner.context.region == "gansu"
    assert planner.context.crop_type == "maize"
    assert planner.context.task_type == "lai_inversion"
    assert planner.context.datasets[0].local_path == str(source)
    assert planner.context.datasets[0].content_type == "image/tiff"
    persisted_run = store.get_run(state["run_id"])
    assert persisted_run is not None
    assert persisted_run.input_message == original_message
    assert persisted_run.input_context.datasets[0].dataset_id == dataset.json()["dataset_id"]


def test_dataset_context_supplies_tool_image_path_without_prompt_path() -> None:
    context = RequestContextV2(datasets=[ResolvedDatasetV2(
        dataset_id="dataset-1",
        display_name="scene.tif",
        local_path="C:/data/scene.tif",
    )])

    payload = ChatFirstPlanner._normalize_tool_input(
        tool_name="prosail.lai_html_report",
        tool_input={},
        message="请反演 LAI",
        request_context=context,
    )

    assert payload["image_path"] == "C:/data/scene.tif"
    assert "C:/data/scene.tif" not in payload["query"]


def test_latest_context_inheritance_uses_session_latest_run_id(tmp_path) -> None:
    """A second submission inherits runtime context without API-only timestamps."""
    store = InMemoryRuntimeStore()
    engine = BoundedRuntimeEngine(
        store=store,
        tool_registry=ToolRegistryV2(definitions={}),
        policy_registry=build_default_policy_registry(),
        agent_registry=build_default_agent_registry(),
        pack_registry=build_default_pack_registry(),
    )
    planner = _CapturingPlanner()
    engine._planner = planner
    app = FastAPI()
    app.state.runtime_store = store
    app.state.runtime_engine = engine
    install_canonical_product_api(app, db_path=str(tmp_path / "product.sqlite3"))

    with TestClient(app) as client:
        conversation = client.post("/api/product/v1/conversations", json={"title": "inherit context"})
        conversation_id = conversation.json()["conversation_id"]
        previous_run = RunDetail(
            run_id="previous-run",
            session_id=conversation_id,
            status="completed",
            input_message="first request",
            input_context=RequestContextV2(
                region="heihe",
                crop_type="maize",
                task_type="lai_inversion",
                image_path="C:/data/selected-scene.tif",
            ),
            output_message="first response",
        )
        store.save_run(previous_run)
        session = store.get_session(conversation_id)
        assert session is not None
        session.latest_run_id = previous_run.run_id
        store.save_session(session)

        submission = client.post(
            f"/api/product/v1/conversations/{conversation_id}/submissions",
            json={
                "input": {"message": "continue with the previous scene"},
                "context": {"inherit": "latest"},
            },
        )
        assert submission.status_code == 201
        submission_id = submission.json()["submission_id"]
        for _ in range(100):
            state = client.get(f"/api/product/v1/submissions/{submission_id}").json()
            if state["status"] in {"completed", "failed"}:
                break
            time.sleep(0.01)
        else:
            raise AssertionError("submission did not become terminal")

    assert state["status"] == "completed"
    inherited_run = store.get_run(state["run_id"])
    assert inherited_run is not None
    assert inherited_run.input_context is not None
    assert inherited_run.input_context.region == "heihe"
    assert inherited_run.input_context.crop_type == "maize"
    assert inherited_run.input_context.task_type == "lai_inversion"
    assert inherited_run.input_context.image_path == "C:/data/selected-scene.tif"
