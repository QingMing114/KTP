"""Composition manifest validation tests.

The manifest is the readable answer to "what is wired in this deployment".
These tests lock the fail-loud rules: unknown capabilities, missing required
providers, misspelled tool names and contradictory exposure lists.
"""

from __future__ import annotations

import pytest

from v2.composition import (
    CompositionError,
    CompositionSpec,
    ToolExposure,
    build_default_composition,
    validate_composition,
)
from v2.seams import SeamRegistry, build_default_seams
from v2.tools.registry import ToolRegistryV2


def _tool_names() -> list[str]:
    return ["ktp.build_report", "prosail.lai_html_report", "workspace.search"]


def _seams_with_tools() -> SeamRegistry:
    return build_default_seams(tools=ToolRegistryV2(definitions={}))


def test_default_composition_declares_expected_capabilities():
    spec = build_default_composition()

    assert spec.name == "ktp-default"
    assert spec.required_capabilities == ["tools"]
    assert spec.tools.default == "model"
    assert spec.tools.disabled == []
    assert spec.tools.endpoint_only == []
    assert spec.middlewares == ["permission", "policy-guard"]


def test_validation_returns_warnings_for_unmentioned_tools():
    warnings = validate_composition(
        build_default_composition(),
        seams=_seams_with_tools(),
        tool_names=_tool_names(),
    )

    assert len(warnings) == 1
    assert "does not mention registered tools" in warnings[0]
    assert "ktp.build_report" in warnings[0]


def test_validation_passes_when_every_tool_is_declared():
    spec = CompositionSpec(
        tools=ToolExposure(
            disabled=["ktp.build_report", "prosail.lai_html_report"],
            endpoint_only=["workspace.search"],
        )
    )

    warnings = validate_composition(spec, seams=_seams_with_tools(), tool_names=_tool_names())

    assert warnings == []


def test_missing_required_capability_fails_loud():
    spec = CompositionSpec(required_capabilities=["tools", "llm"])

    with pytest.raises(CompositionError, match="requires capabilities without providers"):
        validate_composition(spec, seams=_seams_with_tools(), tool_names=_tool_names())


def test_unknown_capability_fails_loud():
    spec = CompositionSpec(optional_capabilities=["telepathy"])

    with pytest.raises(CompositionError, match="unknown capabilities"):
        validate_composition(spec, seams=_seams_with_tools(), tool_names=_tool_names())


def test_unknown_middleware_fails_loud():
    spec = CompositionSpec(middlewares=["permission", "telepathy"])

    with pytest.raises(CompositionError, match="unknown middlewares"):
        validate_composition(spec, seams=_seams_with_tools(), tool_names=_tool_names())


def test_duplicate_middleware_fails_loud():
    spec = CompositionSpec(middlewares=["permission", "permission"])

    with pytest.raises(CompositionError, match="duplicate middlewares"):
        validate_composition(spec, seams=_seams_with_tools(), tool_names=_tool_names())


def test_misspelled_tool_name_fails_loud():
    spec = CompositionSpec(tools=ToolExposure(disabled=["ktp.build_reprot"]))

    with pytest.raises(CompositionError, match="unregistered tools"):
        validate_composition(spec, seams=_seams_with_tools(), tool_names=_tool_names())


def test_disabled_and_endpoint_only_overlap_fails_loud():
    spec = CompositionSpec(
        tools=ToolExposure(
            disabled=["ktp.build_report"],
            endpoint_only=["ktp.build_report"],
        )
    )

    with pytest.raises(CompositionError, match="both disabled and"):
        validate_composition(spec, seams=_seams_with_tools(), tool_names=_tool_names())
