from __future__ import annotations

from jsonschema import Draft202012Validator
import pytest

from schemas.runtime import AgentStepV2, AgentToolCallV2, PermissionPolicy
from v2.agents.registry import build_default_agent_registry
from v2.packs.registry import build_default_pack_registry
from v2.policies.registry import PolicyRegistryV2
from v2.runtime.engine import BoundedRuntimeEngine
from v2.runtime.store import InMemoryRuntimeStore
from v2.tools.registry import ToolRegistryV2, ToolUnavailableError
from v2.tools.remote_sensing.contract import (
    ALGORITHM_TOOL_CONTRACT_VERSION,
    AlgorithmProgressEvent,
    AlgorithmToolInput,
    AlgorithmToolResult,
    ContractInputError,
    ToolExecutionContext,
    build_algorithm_tool_spec,
)
from v2.tools.remote_sensing.probe import ContractProbeState, build_contract_probe_handler


def _spec(**overrides):
    values = {
        "capability_name": "remote_sensing.contract_probe",
        "display_name": "Contract probe",
        "description": "Validate the algorithm contract without running an algorithm.",
        "produces_artifacts": ["text_card"],
        "permissions": ["dataset:read", "artifact:write"],
        "runtime_requirements": {
            "devices": ["cpu"],
            "timeout_seconds": 10,
            "supports_cancellation": True,
        },
        "implementation": {
            "algorithm": "deterministic-contract-probe",
            "version": "1.0.0",
        },
        "visibility": "bounded",
        "surface_visibility": "internal",
    }
    values.update(overrides)
    return build_algorithm_tool_spec(**values)


def _input(*, fail: bool = False) -> dict:
    return {
        "dataset_refs": [
            {
                "dataset_id": "dataset-contract-1",
                "role": "primary",
                "media_type": "application/octet-stream",
            }
        ],
        "parameters": {"fail": fail},
        "output_options": {"include_visualization": False},
    }


class _SequencePlanner:
    def __init__(self, *steps: AgentStepV2) -> None:
        self.steps = list(steps)

    def plan(self, **_kwargs) -> AgentStepV2:
        return self.steps.pop(0)


def test_contract_schemas_are_valid_draft_2020_12_documents() -> None:
    input_schema = AlgorithmToolInput.model_json_schema()
    output_schema = AlgorithmToolResult.model_json_schema()

    Draft202012Validator.check_schema(input_schema)
    Draft202012Validator.check_schema(output_schema)
    assert input_schema["additionalProperties"] is False
    assert output_schema["additionalProperties"] is False
    assert "local_path" not in str(input_schema)


def test_execution_context_and_progress_are_strict_and_bounded() -> None:
    context = ToolExecutionContext(
        execution_id="exec-1",
        trace_id="trace-1",
        user_id="user-1",
        permissions=["dataset:read"],
    )
    event = AlgorithmProgressEvent(
        execution_id=context.execution_id,
        stage="running",
        progress=0.5,
        message="halfway",
    )

    assert event.contract_version == ALGORITHM_TOOL_CONTRACT_VERSION
    with pytest.raises(ValueError):
        AlgorithmProgressEvent(
            execution_id="exec-1",
            stage="running",
            progress=1.1,
        )


def test_algorithm_spec_exposes_frozen_metadata_and_valid_schemas() -> None:
    spec = _spec()

    assert spec.contract_version == ALGORITHM_TOOL_CONTRACT_VERSION
    assert spec.availability == "available"
    assert spec.permissions == ["dataset:read", "artifact:write"]
    assert spec.runtime_requirements["supports_cancellation"] is True
    Draft202012Validator.check_schema(spec.input_schema)
    Draft202012Validator.check_schema(spec.output_schema)

    with pytest.raises(ValueError, match="must explain why"):
        _spec(availability="unavailable")
    with pytest.raises(ValueError, match="remote_sensing"):
        _spec(capability_name="KDD2020")
    with pytest.raises(ValueError, match="permission"):
        _spec(permissions=[])


def test_registry_rejects_invalid_contract_input_before_handler() -> None:
    called = False

    def handler(**_kwargs):
        nonlocal called
        called = True

    registry = ToolRegistryV2(definitions={})
    spec = _spec()
    registry.register(spec.name, spec, handler)

    with pytest.raises(ContractInputError, match="dataset_refs"):
        registry.invoke(tool_name=spec.name, tool_input={"parameters": {}})
    assert called is False


@pytest.mark.parametrize(
    "forbidden_parameters",
    [
        {"local_path": "C:\\data\\scene.tif"},
        {"nested": {"token": "secret-value"}},
        {"weights": "/srv/models/model.pt"},
        {"command": "python infer.py"},
    ],
)
def test_registry_rejects_paths_commands_and_credentials(forbidden_parameters: dict) -> None:
    registry = ToolRegistryV2(definitions={})
    spec = _spec()
    registry.register(spec.name, spec, lambda **_kwargs: None)
    tool_input = _input()
    tool_input["parameters"] = forbidden_parameters

    with pytest.raises(ContractInputError, match="forbidden"):
        registry.invoke(tool_name=spec.name, tool_input=tool_input)


def test_unavailable_contract_tool_is_not_invoked() -> None:
    called = False

    def handler(**_kwargs):
        nonlocal called
        called = True

    registry = ToolRegistryV2(definitions={})
    spec = _spec(
        availability="unavailable",
        unavailable_reason="algorithm, weights, and dataset are not selected",
    )
    registry.register(spec.name, spec, handler)

    with pytest.raises(ToolUnavailableError, match="weights"):
        registry.invoke(tool_name=spec.name, tool_input=_input())
    assert called is False


def test_probe_success_uses_bridge_and_cleans_workspace() -> None:
    state = ContractProbeState()
    registry = ToolRegistryV2(definitions={})
    spec = _spec()
    registry.register(spec.name, spec, build_contract_probe_handler(state))

    observation, artifacts = registry.invoke(tool_name=spec.name, tool_input=_input())
    result = AlgorithmToolResult.model_validate(observation.payload["algorithm_result"])
    Draft202012Validator(spec.output_schema).validate(result.model_dump(mode="json"))

    assert observation.status == "success"
    assert result.status == "succeeded"
    assert result.provenance is not None
    assert result.provenance.capability_name == spec.name
    assert artifacts[0].artifact_type == "text_card"
    assert state.cleanup_completed is True
    assert state.last_workspace is not None
    assert not state.last_workspace.exists()


def test_probe_failure_preserves_error_code_and_cleans_workspace() -> None:
    state = ContractProbeState()
    registry = ToolRegistryV2(definitions={})
    spec = _spec()
    registry.register(spec.name, spec, build_contract_probe_handler(state))

    observation, artifacts = registry.invoke(tool_name=spec.name, tool_input=_input(fail=True))
    result = AlgorithmToolResult.model_validate(observation.payload["algorithm_result"])
    Draft202012Validator(spec.output_schema).validate(result.model_dump(mode="json"))

    assert observation.status == "error"
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "INFERENCE_FAILED"
    assert artifacts == []
    assert state.cleanup_completed is True
    assert state.last_workspace is not None
    assert not state.last_workspace.exists()


def test_probe_runs_through_bounded_runtime_and_emits_lifecycle_events() -> None:
    state = ContractProbeState()
    registry = ToolRegistryV2(definitions={})
    spec = _spec(surface_visibility="all")
    registry.register(spec.name, spec, build_contract_probe_handler(state))
    store = InMemoryRuntimeStore()
    store.create_session(session_id="contract-session", title="contract", created_by="test")
    engine = BoundedRuntimeEngine(
        store=store,
        tool_registry=registry,
        policy_registry=PolicyRegistryV2(policies=[PermissionPolicy(
            name="contract-test",
            description="Contract test policy.",
            max_replans=1,
            max_delegations=0,
        )]),
        agent_registry=build_default_agent_registry(),
        pack_registry=build_default_pack_registry(),
    )
    engine._planner = _SequencePlanner(
        AgentStepV2(
            action="call_tools",
            reasoning="validate contract",
            tool_calls=[AgentToolCallV2(tool_name=spec.name, tool_input=_input())],
        ),
        AgentStepV2(action="reply", reasoning="done", response_message="contract verified"),
    )

    events = list(engine.stream(
        session_id="contract-session",
        user_message="run the contract probe",
        user_id="test",
    ))
    event_names = [event.event for event in events]
    final_run = events[-1].run

    assert "tool.started" in event_names
    assert "tool.completed" in event_names
    assert "artifact.available" in event_names
    assert final_run is not None
    assert final_run.status == "completed"
    assert final_run.observation is not None
    assert final_run.observation.payload["algorithm_result"]["contract_version"] == ALGORITHM_TOOL_CONTRACT_VERSION
    assert state.cleanup_completed is True
