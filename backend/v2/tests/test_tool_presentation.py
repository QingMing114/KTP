"""Tool presentation declaration tests.

Presentation is optional: tools without it keep their current behavior. The
declaration is what lets a renderer be chosen by contract instead of by hard
coding a tool or step name in the client.
"""

from __future__ import annotations

from schemas.runtime import ToolPresentation, ToolSpecV2
from v2.runtime.planner import ChatFirstPlanner
from v2.tools.registry import build_default_tool_registry


def _spec(**overrides) -> ToolSpecV2:
    payload = {
        "name": "demo.tool",
        "description": "Demo tool.",
        "visibility": "public",
    }
    payload.update(overrides)
    return ToolSpecV2(**payload)


def test_presentation_defaults_to_absent():
    spec = _spec()

    assert spec.presentation is None
    assert spec.model_dump()["presentation"] is None


def test_presentation_round_trips_through_the_spec():
    spec = _spec(
        presentation=ToolPresentation(
            card_kind="report",
            summary_fields=["report_title"],
            progress_phases=["生成报告"],
            result_renderer="report_card",
            expandable=False,
        )
    )

    dumped = spec.model_dump()
    restored = ToolSpecV2.model_validate(dumped)

    assert restored.presentation is not None
    assert restored.presentation.card_kind == "report"
    assert restored.presentation.summary_fields == ["report_title"]
    assert restored.presentation.result_renderer == "report_card"
    assert restored.presentation.expandable is False


def test_presentation_defaults_inside_the_model():
    presentation = ToolPresentation()

    assert presentation.card_kind == "generic"
    assert presentation.summary_fields == []
    assert presentation.progress_phases == []
    assert presentation.result_renderer is None
    assert presentation.expandable is True


def test_registry_declares_presentation_for_representative_tools():
    registry = build_default_tool_registry()

    lai_report = registry.get_definition("prosail.lai_html_report").spec
    assert lai_report.presentation is not None
    assert lai_report.presentation.card_kind == "report"
    assert lai_report.presentation.result_renderer == "lai_report"
    assert lai_report.presentation.progress_phases

    build_report = registry.get_definition("ktp.build_report").spec
    assert build_report.presentation is not None
    assert build_report.presentation.result_renderer == "report_card"


def test_planner_tool_summary_tolerates_presentation():
    spec = _spec(presentation=ToolPresentation(card_kind="analysis"))

    summary = ChatFirstPlanner._compact_tool_summary(spec)

    assert isinstance(summary, dict)
    assert summary.get("name") == "demo.tool"
