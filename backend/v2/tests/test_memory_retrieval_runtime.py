from __future__ import annotations

from pathlib import Path

from ktp_backend.runtime_host import build_backend_runtime_host
from schemas.runtime import AgentStepV2, PermissionPolicy
from v2.apps.api.config import V2ApiSettings
from v2.agents.registry import build_default_agent_registry
from v2.packs.registry import build_default_pack_registry
from v2.policies.registry import PolicyRegistryV2
from v2.runtime.engine import BoundedRuntimeEngine
from v2.runtime.store import InMemoryRuntimeStore
from v2.tools.registry import ToolRegistryV2


class _CapturingPlanner:
    def __init__(self) -> None:
        self.memory_context = ""

    def plan(self, **kwargs) -> AgentStepV2:
        self.memory_context = kwargs["memory_context"]
        return AgentStepV2(
            action="reply",
            reasoning="answer from retrieved reference",
            response_message="The dataset endpoint is POST /datasets.",
        )


def test_runtime_passes_retrieved_markdown_to_planner_without_writing(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text(
        "# Index\n\n- [Protocol](protocol.md)\n",
        encoding="utf-8",
    )
    protocol = tmp_path / "protocol.md"
    protocol.write_text(
        "# Dataset protocol\n\nCreate a dataset with `POST /datasets`.\n",
        encoding="utf-8",
    )
    store = InMemoryRuntimeStore()
    store.create_session(session_id="memory-session", title="memory", created_by="test")
    engine = BoundedRuntimeEngine(
        store=store,
        tool_registry=ToolRegistryV2(definitions={}),
        policy_registry=PolicyRegistryV2(policies=[PermissionPolicy(
            name="memory-test",
            description="Memory retrieval test policy.",
            max_replans=1,
            max_delegations=1,
        )]),
        agent_registry=build_default_agent_registry(),
        pack_registry=build_default_pack_registry(),
        memory_dir=str(tmp_path),
    )
    planner = _CapturingPlanner()
    engine._planner = planner

    run = engine.run(
        session_id="memory-session",
        user_message="Which endpoint creates a dataset?",
        user_id="test",
    )

    assert "POST /datasets" in planner.memory_context
    assert any(event.event == "memory_context_injected" for event in run.trace)
    assert protocol.read_text(encoding="utf-8") == "# Dataset protocol\n\nCreate a dataset with `POST /datasets`.\n"


def test_runtime_host_enables_configured_read_only_memory_directory(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text("# Index\n", encoding="utf-8")

    host = build_backend_runtime_host(settings_override=V2ApiSettings(
        memory_dir=str(tmp_path),
        memory_auto_write_enabled=False,
    ))

    assert host.runtime_engine._memory_manager is not None
    assert host.runtime_engine._memory_manager.is_loaded
    assert host.runtime_engine._memory_auto_write_enabled is False
