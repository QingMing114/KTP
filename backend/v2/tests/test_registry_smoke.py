from __future__ import annotations

from v2.agents.registry import build_default_agent_registry
from v2.packs.registry import build_default_pack_registry
from v2.policies.registry import build_default_policy_registry
from v2.tools.registry import build_default_tool_registry


def test_default_v2_registries_are_populated() -> None:
    assert len(build_default_agent_registry().list_profiles()) >= 2
    tools = build_default_tool_registry().list_tools()
    assert len(tools) >= 9
    assert any(tool.name == "ktp.analysis_pipeline" and tool.is_macro for tool in tools)
    assert any(tool.name == "ktp.explain_knowledge" for tool in tools)
    assert any(tool.name == "ktp.retrieve_knowledge" for tool in tools)
    assert any(tool.name == "ktp.build_visualization" for tool in tools)
    assert len(build_default_policy_registry().list_policies()) == 1
    packs = build_default_pack_registry().list_packs()
    assert len(packs) >= 2
    assert any(
        pack.name == "ktp"
        and "ktp.analysis_pipeline" in pack.entry_tools
        and "ktp.explain_knowledge" in pack.entry_tools
        and "ktp.trigger_training" in pack.entry_tools
        for pack in packs
    )
