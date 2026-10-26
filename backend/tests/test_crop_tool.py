"""Crop tool registration tests (A2/A3).

The tool is host-invoked: the caller supplies the validated STAC item, and the
handler delegates to the single classification implementation. Visibility stays
``debug`` so the planner is not offered a tool it cannot satisfy yet.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from api.canonical.router import install_canonical_product_api
from runtime.crop_classification import CropClassificationOutcome
from v2.tools.crop_tool import (
    CROP_TOOL_NAME,
    build_crop_handler,
    build_crop_tool_spec,
    configure_crop_tool,
    register_unavailable_crop_tool,
)
from v2.tools.registry import ToolRegistryV2, ToolUnavailableError


def _inputs(**overrides):
    payload = {
        "run_id": "run-1",
        "imagery_item_id": "item-1",
        "imagery_snapshot": {
            "item_id": "item-1",
            "collection": "sentinel-2-l2a",
            "acquired_at": "2026-05-14T00:00:00Z",
            "cloud_cover": 3.0,
            "asset_fingerprint": "sha256:abc",
        },
        "aoi_geometry": {"type": "Polygon", "coordinates": []},
        "area_hectares": 12.5,
        "farm_id": "farm-1",
        "observed_at": "2026-05-14T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def _outcome():
    return CropClassificationOutcome(
        result={"crop_decision": {"final_name_zh": "玉米", "source": "llm"}, "report_uri": "artifact://r1"},
        decision={"final_name_zh": "玉米", "source": "llm"},
        report_references={"report_uri": "artifact://r1"},
    )


def test_spec_is_host_only_and_declares_permissions_and_presentation():
    spec = build_crop_tool_spec(available=True)

    assert spec.name == CROP_TOOL_NAME
    assert spec.category == "remote_sensing"
    assert spec.surface_visibility == "debug"
    assert spec.availability == "available"
    assert spec.permissions == ["dataset:read", "artifact:write"]
    assert spec.presentation is not None
    assert spec.presentation.result_renderer == "crop_decision"
    assert "additionalProperties" in str(spec.input_schema)


def test_unavailable_spec_reports_a_reason():
    spec = build_crop_tool_spec(available=False, unavailable_reason="no artifact store")

    assert spec.availability == "unavailable"
    assert spec.unavailable_reason == "no artifact store"


def test_model_visibility_is_an_explicit_gate():
    assert build_crop_tool_spec(available=True).surface_visibility == "debug"
    assert build_crop_tool_spec(available=True, model_visible=True).surface_visibility == "all"


def test_handler_requires_the_host_resolved_item(tmp_path):
    handler = build_crop_handler(artifact_store=object(), artifact_root=tmp_path)

    with pytest.raises(RuntimeError, match="host-resolved imagery item"):
        handler(**_inputs())


def test_handler_delegates_to_the_single_implementation(monkeypatch, tmp_path):
    calls: dict[str, object] = {}

    def fake_classify(**kwargs):
        calls.update(kwargs)
        return _outcome()

    monkeypatch.setattr("v2.tools.crop_tool.classify_crop", fake_classify)
    handler = build_crop_handler(artifact_store=object(), artifact_root=tmp_path)
    item = object()

    observation, artifacts = handler(item=item, **_inputs())

    assert observation.status == "success"
    assert observation.payload["report_uri"] == "artifact://r1"
    assert observation.summary == "作物识别已完成：判定为玉米"
    assert artifacts == []
    assert calls["source"].item is item
    assert calls["output_dir"] == tmp_path / "crop" / "run-1"
    assert calls["imagery_item_id"] == "item-1"
    assert calls["provenance"]["item_id"] == "item-1"
    assert calls["provenance"]["asset_fingerprint"] == "sha256:abc"


def test_handler_forwards_progress_and_an_explicit_output_dir(monkeypatch, tmp_path):
    calls: dict[str, object] = {}

    def fake_classify(**kwargs):
        calls.update(kwargs)
        return _outcome()

    monkeypatch.setattr("v2.tools.crop_tool.classify_crop", fake_classify)
    handler = build_crop_handler(artifact_store=object(), artifact_root=tmp_path)
    events: list[tuple[str, int]] = []
    output_dir = tmp_path / "custom"

    handler(
        item=object(),
        progress_callback=lambda detail, percent: events.append((detail, percent)),
        **_inputs(output_dir=str(output_dir)),
    )

    assert calls["output_dir"] == output_dir
    assert callable(calls["progress_callback"])
    calls["progress_callback"]("读取影像", 10)
    assert events == [("读取影像", 10)]


def test_configure_registers_a_callable_tool(monkeypatch, tmp_path):
    monkeypatch.setattr("v2.tools.crop_tool.classify_crop", lambda **kwargs: _outcome())
    registry = ToolRegistryV2(definitions={})

    configure_crop_tool(registry, artifact_store=object(), artifact_root=tmp_path)
    observation, _ = registry.invoke(tool_name=CROP_TOOL_NAME, tool_input={"item": object(), **_inputs()})

    assert observation.status == "success"


def test_registry_rejects_an_unconfigured_crop_tool(tmp_path):
    registry = ToolRegistryV2(definitions={})
    register_unavailable_crop_tool(registry, reason="artifact store missing")

    with pytest.raises(ToolUnavailableError, match="artifact store missing"):
        registry.invoke(tool_name=CROP_TOOL_NAME, tool_input={"item": object(), **_inputs()})


def test_canonical_install_registers_the_crop_tool(tmp_path):
    app = FastAPI()
    install_canonical_product_api(app, db_path=str(tmp_path / "product.sqlite3"), auth_required=False)

    registry = app.state.tool_registry
    assert CROP_TOOL_NAME in {spec.name for spec in registry.list_tools()}
    assert registry.get_definition(CROP_TOOL_NAME).spec.availability == "available"
