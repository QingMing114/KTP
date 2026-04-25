"""Unit tests for bounded tool registry discovery."""

from __future__ import annotations

from services.tool_registry.registry import get_tool_spec, list_tool_specs, select_relevant_tools


def test_tool_registry_contains_expected_core_tools() -> None:
    tools = list_tool_specs()
    names = {tool.name for tool in tools}

    assert "direct_answer" in names
    assert "rag_search" in names
    assert "run_remote_sensing_workflow" in names


def test_tool_registry_lookup_by_name() -> None:
    tool = get_tool_spec("rag_search")

    assert tool is not None
    assert tool.name == "rag_search"
    assert "sources" in tool.output_schema


def test_select_relevant_tools_prefers_workflow_for_analysis_request() -> None:
    tools = select_relevant_tools(
        user_message="请分析河北省小麦病害情况，并生成报告和置信度说明。",
        task_type="crop_health_detection",
        limit=3,
    )

    assert tools
    assert tools[0].name == "run_remote_sensing_workflow"
