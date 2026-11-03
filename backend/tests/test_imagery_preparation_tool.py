"""Imagery preparation tool tests (P1-P5).

Preparation is host-invoked: the caller supplies the validated STAC item. The
workflow step is the production entry and now invokes this tool through the
registry; the end-to-end workflow coverage lives in
``test_analysis_workflow_api.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from api.canonical.router import install_canonical_product_api
from runtime.imagery_preparation import ImageryPreparationOutcome, prepare_imagery
from v2.tools.crop_tool import CROP_TOOL_NAME
from v2.tools.imagery_preparation_tool import (
    IMAGERY_PREPARATION_TOOL_NAME,
    ImageryPreparationToolInput,
    build_imagery_preparation_handler,
    build_imagery_preparation_tool_spec,
    configure_imagery_preparation_tool,
    register_unavailable_imagery_preparation_tool,
)
from v2.tools.imagery_search_tool import IMAGERY_SEARCH_TOOL_NAME
from v2.tools.registry import ToolRegistryV2, ToolUnavailableError

AOI = {
    "type": "Polygon",
    "coordinates": [[[100.0, 38.0], [100.01, 38.0], [100.01, 38.01], [100.0, 38.01], [100.0, 38.0]]],
}


class _Store:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def register(self, run_id: str, artifact: object) -> str:
        self.calls.append((run_id, artifact))
        return f"art-{len(self.calls)}"


def _patch_reader(monkeypatch, calls: list[dict]) -> None:
    def fake_read(*, item, geometry, output_path, target_resolution_m, progress_callback=None, **_kwargs):
        calls.append(
            {
                "item": item,
                "geometry": geometry,
                "output_path": Path(output_path),
                "resolution_m": target_resolution_m,
            }
        )
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"tif")
        if progress_callback is not None:
            progress_callback("读取 Sentinel 波段", 50)
        return Path(output_path)

    monkeypatch.setattr("runtime.imagery_preparation.read_prosail_reflectance_aoi", fake_read)


def _outcome(tmp_path: Path) -> ImageryPreparationOutcome:
    return ImageryPreparationOutcome(
        reflectance_path=tmp_path / "reflectance.tif",
        artifact_id="art-9",
        bands=["B02", "B03", "B04", "B07", "B08"],
        resolution_m=20,
        result={
            "artifact_id": "art-9",
            "bands": ["B02", "B03", "B04", "B07", "B08"],
            "resolution_m": 20,
            "parameters": {},
            "imagery_provenance": {},
        },
    )


def test_service_reads_and_registers_the_shared_raster(monkeypatch, tmp_path):
    calls: list[dict] = []
    _patch_reader(monkeypatch, calls)
    store = _Store()
    events: list[tuple[str, int]] = []

    outcome = prepare_imagery(
        item=object(),
        geometry=AOI,
        output_dir=tmp_path / "workflows" / "wf-1",
        run_id="wf-1",
        artifact_store=store,
        target_resolution_m=20,
        parameters={"target_resolution_m": 20},
        provenance={"item_id": "S2B-1"},
        progress_callback=lambda detail, percent: events.append((detail, percent)),
    )

    assert outcome.reflectance_path == tmp_path / "workflows" / "wf-1" / "reflectance.tif"
    assert outcome.reflectance_path.is_file()
    assert outcome.artifact_id == "art-1"
    assert store.calls[0][0] == "wf-1"
    assert store.calls[0][1].artifact_type == "reflectance_tif"
    assert outcome.result["bands"] == ["B02", "B03", "B04", "B07", "B08"]
    assert outcome.result["resolution_m"] == 20
    assert outcome.result["imagery_provenance"] == {"item_id": "S2B-1"}
    assert calls[0]["geometry"] == AOI
    assert calls[0]["resolution_m"] == 20
    assert events == [("读取 Sentinel 波段", 50)]


def test_spec_declares_artifact_and_permissions():
    spec = build_imagery_preparation_tool_spec(available=True)

    assert spec.name == IMAGERY_PREPARATION_TOOL_NAME
    assert spec.category == "remote_sensing"
    assert spec.surface_visibility == "debug"
    assert spec.safety_level == "caution"
    assert spec.permissions == ["dataset:read", "artifact:write"]
    assert spec.produces_artifacts == ["reflectance_tif"]
    assert spec.presentation is not None
    assert spec.presentation.result_renderer == "imagery_prepared"
    assert spec.input_schema["additionalProperties"] is False


def test_model_visibility_is_an_explicit_gate():
    assert build_imagery_preparation_tool_spec(available=True).surface_visibility == "debug"
    assert (
        build_imagery_preparation_tool_spec(available=True, model_visible=True).surface_visibility
        == "all"
    )


def test_handler_delegates_and_defaults_the_output_directory(monkeypatch, tmp_path):
    calls: dict[str, object] = {}

    def fake_prepare(**kwargs):
        calls.update(kwargs)
        return _outcome(tmp_path)

    monkeypatch.setattr("v2.tools.imagery_preparation_tool.prepare_imagery", fake_prepare)
    handler = build_imagery_preparation_handler(artifact_store=_Store(), artifact_root=tmp_path)
    item = object()

    observation, artifacts = handler(
        item=item,
        run_id="wf-1",
        aoi_geometry=AOI,
        target_resolution_m=20,
        parameters={"target_resolution_m": 20},
        provenance={"item_id": "S2B-1"},
    )

    assert observation.status == "success"
    assert observation.payload["artifact_id"] == "art-9"
    assert "影像已准备" in observation.summary
    assert artifacts == []
    assert calls["item"] is item
    assert calls["output_dir"] == tmp_path / "workflows" / "wf-1"
    assert calls["run_id"] == "wf-1"


def test_handler_requires_the_host_resolved_item(tmp_path):
    handler = build_imagery_preparation_handler(artifact_store=_Store(), artifact_root=tmp_path)

    with pytest.raises(RuntimeError, match="host-resolved imagery item"):
        handler(run_id="wf-1", aoi_geometry=AOI)


def test_configure_registers_a_callable_tool(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "v2.tools.imagery_preparation_tool.prepare_imagery",
        lambda **kwargs: _outcome(tmp_path),
    )
    registry = ToolRegistryV2(definitions={})
    configure_imagery_preparation_tool(
        registry, artifact_store=_Store(), artifact_root=tmp_path
    )

    observation, _ = registry.invoke(
        tool_name=IMAGERY_PREPARATION_TOOL_NAME,
        tool_input={"item": object(), "run_id": "wf-1", "aoi_geometry": AOI},
    )

    assert observation.status == "success"


def test_registry_rejects_an_unconfigured_preparation_tool():
    registry = ToolRegistryV2(definitions={})
    register_unavailable_imagery_preparation_tool(registry, reason="no artifact store")

    with pytest.raises(ToolUnavailableError, match="no artifact store"):
        registry.invoke(
            tool_name=IMAGERY_PREPARATION_TOOL_NAME,
            tool_input={"item": object(), "run_id": "wf-1", "aoi_geometry": AOI},
        )


def test_canonical_install_registers_the_three_professional_tools(tmp_path):
    app = FastAPI()
    install_canonical_product_api(
        app, db_path=str(tmp_path / "product.sqlite3"), auth_required=False
    )

    names = {spec.name for spec in app.state.tool_registry.list_tools()}
    assert {CROP_TOOL_NAME, IMAGERY_SEARCH_TOOL_NAME, IMAGERY_PREPARATION_TOOL_NAME} <= names
    assert (
        app.state.tool_registry.get_definition(IMAGERY_PREPARATION_TOOL_NAME).spec.availability
        == "available"
    )
