from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.canonical.router import install_canonical_product_api
from schemas.runtime import AgentStepV2, AgentToolCallV2, RequestContextV2, ResolvedDatasetV2, RunDetail
from v2.agents.registry import build_default_agent_registry
from v2.packs.registry import build_default_pack_registry
from v2.policies.registry import build_default_policy_registry
from v2.runtime.engine import BoundedRuntimeEngine
from v2.runtime.planner import ChatFirstPlanner
from v2.runtime.store import InMemoryRuntimeStore
from v2.tools.registry import ToolRegistryV2
from v2.tools.remote_sensing.contract import build_algorithm_tool_spec
from v2.tools.remote_sensing.dataset_resolver import AlgorithmDatasetResolver
from v2.tools.remote_sensing.probe import ContractProbeState, build_contract_probe_handler


class _CapturingPlanner:
    def __init__(self) -> None:
        self.message: str | None = None
        self.context: RequestContextV2 | None = None

    def plan(self, *, message: str, request_context: RequestContextV2, **_kwargs) -> AgentStepV2:
        self.message = message
        self.context = request_context
        return AgentStepV2(action="reply", reasoning="test", response_message="accepted")


class _SequencePlanner:
    def __init__(self, *steps: AgentStepV2) -> None:
        self.steps = list(steps)

    def plan(self, **_kwargs) -> AgentStepV2:
        return self.steps.pop(0)


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


def test_canonical_boundary_injects_trusted_dataset_context_and_grants(tmp_path) -> None:
    captured_paths = []
    probe_state = ContractProbeState()
    probe_handler = build_contract_probe_handler(probe_state)
    resolver = AlgorithmDatasetResolver()

    def handler(tool_input, execution_context, execution_control):
        resolved = resolver.resolve(
            tool_input,
            execution_context,
            required_roles={"primary"},
        )
        captured_paths.extend(item.path for item in resolved)
        return probe_handler(tool_input, execution_context, execution_control)

    spec = build_algorithm_tool_spec(
        capability_name="remote_sensing.contract_probe",
        display_name="Contract probe",
        description="Exercise the trusted canonical algorithm boundary.",
        produces_artifacts=["text_card"],
        permissions=["dataset:read", "artifact:write"],
        runtime_requirements={
            "devices": ["cpu"],
            "timeout_seconds": 10,
            "supports_cancellation": True,
        },
        implementation={"algorithm": "probe", "version": "1.0.0"},
        visibility="bounded",
        surface_visibility="all",
    )
    registry = ToolRegistryV2(definitions={})
    registry.register(spec.name, spec, handler)
    store = InMemoryRuntimeStore()
    engine = BoundedRuntimeEngine(
        store=store,
        tool_registry=registry,
        policy_registry=build_default_policy_registry(),
        agent_registry=build_default_agent_registry(),
        pack_registry=build_default_pack_registry(),
    )
    engine._planner = _SequencePlanner(
        AgentStepV2(
            action="call_tools",
            reasoning="exercise trusted context",
            tool_calls=[AgentToolCallV2(
                tool_name=spec.name,
                tool_input={
                    "dataset_refs": [{"dataset_id": "placeholder", "role": "primary"}],
                    "parameters": {},
                    "output_options": {},
                },
            )],
        ),
        AgentStepV2(action="reply", reasoning="done", response_message="accepted"),
    )
    app = FastAPI()
    app.state.runtime_store = store
    app.state.runtime_engine = engine
    install_canonical_product_api(
        app,
        db_path=str(tmp_path / "product.sqlite3"),
        auth_required=True,
        auth_token="product-test-token",
    )
    source = tmp_path / "trusted-scene.tif"
    source.write_bytes(b"scene")
    headers = {"Authorization": "Bearer product-test-token"}

    with TestClient(app) as client:
        conversation = client.post(
            "/api/product/v1/conversations",
            headers=headers,
            json={"title": "trusted context"},
        )
        dataset = client.post(
            "/api/product/v1/datasets",
            headers=headers,
            json={
                "source": {"kind": "local_path", "uri": str(source)},
                "display_name": "trusted-scene.tif",
                "metadata": {"content_type": "image/tiff"},
            },
        )
        dataset_id = dataset.json()["dataset_id"]
        engine._planner.steps[0].tool_calls[0].tool_input["dataset_refs"][0]["dataset_id"] = dataset_id
        submission = client.post(
            f"/api/product/v1/conversations/{conversation.json()['conversation_id']}/submissions",
            headers=headers,
            json={
                "input": {
                    "message": "run trusted probe",
                    "refs": [{"type": "dataset", "id": dataset_id}],
                }
            },
        )
        assert submission.status_code == 201
        submission_id = submission.json()["submission_id"]
        for _ in range(100):
            state = client.get(
                f"/api/product/v1/submissions/{submission_id}",
                headers=headers,
            ).json()
            if state["status"] in {"completed", "failed"}:
                break
            time.sleep(0.01)
        else:
            raise AssertionError("submission did not become terminal")

    assert state["status"] == "completed"
    assert captured_paths == [source.resolve()]
    assert probe_state.cleanup_completed is True
