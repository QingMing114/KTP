"""LAI inversion tool tests (P1-P5).

The inversion runs on an already-prepared reflectance raster, so the tool is
host-invoked. Both production entries (the standalone analysis worker and the
workflow step) call it through the registry; pixel-level progress stays a host
extra so the SSE stream keeps its counts.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from api.canonical.router import install_canonical_product_api
from runtime.lai_inversion import LAIInversionError, run_lai_inversion
from schemas.runtime import ObservationV2, PackArtifactView
from v2.tools.crop_tool import CROP_TOOL_NAME
from v2.tools.imagery_preparation_tool import IMAGERY_PREPARATION_TOOL_NAME
from v2.tools.imagery_search_tool import IMAGERY_SEARCH_TOOL_NAME
from v2.tools.lai_inversion_tool import (
    LAI_INVERSION_TOOL_NAME,
    build_lai_inversion_tool_spec,
    configure_lai_inversion_tool,
    register_unavailable_lai_inversion_tool,
)
from v2.tools.registry import ToolRegistryV2, ToolUnavailableError
from v2.tools.workflow_report_tool import WORKFLOW_REPORT_TOOL_NAME


class _Store:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def register(self, run_id: str, artifact: object) -> str:
        self.calls.append((run_id, artifact))
        return f"art-{artifact.artifact_type}"


def _produced(tmp_path: Path) -> dict[str, Path]:
    files = {
        "report_path": tmp_path / "lai_report.html",
        "lai_raster_path": tmp_path / "lai.tif",
        "lai_preview_path": tmp_path / "lai.png",
    }
    for path in files.values():
        path.write_bytes(b"x")
    return files


def _fake_report(tmp_path: Path):
    files = _produced(tmp_path)

    def fake(**kwargs):
        observation = ObservationV2(
            source="prosail.lai_html_report",
            status="success",
            summary="ok",
            payload={
                "report_path": str(files["report_path"]),
                "lai_raster_path": str(files["lai_raster_path"]),
                "lai_preview_path": str(files["lai_preview_path"]),
                "lai_mean": 2.5,
            },
        )
        views = [
            PackArtifactView(
                pack_name="remote_sensing",
                artifact_type=kind,
                title=kind,
                uri=str(files[key]),
            )
            for kind, key in (
                ("lai_html_report", "report_path"),
                ("lai_raster", "lai_raster_path"),
                ("lai_preview", "lai_preview_path"),
            )
        ]
        return observation, views

    return fake


def test_service_registers_the_three_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr("runtime.lai_inversion.run_lai_html_report", _fake_report(tmp_path))
    store = _Store()

    outcome = run_lai_inversion(
        reflectance_path=tmp_path / "reflectance.tif",
        output_dir=tmp_path / "lai",
        run_id="run-1",
        artifact_store=store,
    )

    assert outcome.payload["lai_mean"] == 2.5
    assert set(outcome.artifact_ids) == {"lai_html_report", "lai_raster", "lai_preview"}
    assert [run_id for run_id, _ in store.calls] == ["run-1", "run-1", "run-1"]


def test_service_rejects_incomplete_output_files(monkeypatch, tmp_path):
    fake = _fake_report(tmp_path)
    monkeypatch.setattr(
        "runtime.lai_inversion.run_lai_html_report",
        lambda **kwargs: (
            fake(**kwargs)[0].model_copy(update={"payload": {"lai_mean": 1.0}}),
            [],
        ),
    )

    with pytest.raises(LAIInversionError, match="文件校验"):
        run_lai_inversion(
            reflectance_path=tmp_path / "reflectance.tif",
            output_dir=tmp_path / "lai",
            run_id="run-1",
            artifact_store=_Store(),
        )


def test_service_rejects_a_failed_observation(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "runtime.lai_inversion.run_lai_html_report",
        lambda **kwargs: (
            ObservationV2(source="prosail.lai_html_report", status="error", summary="反演失败"),
            [],
        ),
    )

    with pytest.raises(LAIInversionError, match="反演失败"):
        run_lai_inversion(
            reflectance_path=tmp_path / "reflectance.tif",
            output_dir=tmp_path / "lai",
            run_id="run-1",
            artifact_store=_Store(),
        )


def test_spec_declares_artifacts_and_permissions():
    spec = build_lai_inversion_tool_spec(available=True)

    assert spec.name == LAI_INVERSION_TOOL_NAME
    assert spec.category == "remote_sensing"
    assert spec.surface_visibility == "debug"
    assert spec.safety_level == "caution"
    assert spec.permissions == ["dataset:read", "artifact:write"]
    assert set(spec.produces_artifacts) == {"lai_html_report", "lai_raster", "lai_preview"}
    assert spec.presentation is not None
    assert spec.presentation.result_renderer == "lai_report"
    assert spec.input_schema["additionalProperties"] is False


def test_model_visibility_is_an_explicit_gate():
    assert build_lai_inversion_tool_spec(available=True).surface_visibility == "debug"
    assert (
        build_lai_inversion_tool_spec(available=True, model_visible=True).surface_visibility == "all"
    )


def test_configure_registers_a_callable_tool(monkeypatch, tmp_path):
    monkeypatch.setattr("runtime.lai_inversion.run_lai_html_report", _fake_report(tmp_path))
    registry = ToolRegistryV2(definitions={})
    configure_lai_inversion_tool(registry, artifact_store=_Store())

    observation, artifacts = registry.invoke(
        tool_name=LAI_INVERSION_TOOL_NAME,
        tool_input={
            "run_id": "run-1",
            "reflectance_path": str(tmp_path / "reflectance.tif"),
            "output_dir": str(tmp_path / "lai"),
        },
    )

    assert observation.status == "success"
    assert observation.payload["result"]["lai_mean"] == 2.5
    assert artifacts == []


def test_handler_translates_uniform_progress_when_no_pixel_callback(monkeypatch, tmp_path):
    monkeypatch.setattr("runtime.lai_inversion.run_lai_html_report", _fake_report(tmp_path))
    registry = ToolRegistryV2(definitions={})
    configure_lai_inversion_tool(registry, artifact_store=_Store())
    events: list[tuple[str, int]] = []

    registry.invoke(
        tool_name=LAI_INVERSION_TOOL_NAME,
        tool_input={
            "run_id": "run-1",
            "reflectance_path": str(tmp_path / "reflectance.tif"),
            "output_dir": str(tmp_path / "lai"),
        },
        progress_callback=lambda detail, percent: events.append((detail, percent)),
    )

    assert events and events[-1][1] == 100


def test_registry_rejects_an_unconfigured_inversion_tool():
    registry = ToolRegistryV2(definitions={})
    register_unavailable_lai_inversion_tool(registry, reason="no artifact store")

    with pytest.raises(ToolUnavailableError, match="no artifact store"):
        registry.invoke(
            tool_name=LAI_INVERSION_TOOL_NAME,
            tool_input={
                "run_id": "run-1",
                "reflectance_path": "/tmp/r.tif",
                "output_dir": "/tmp/lai",
            },
        )


def test_canonical_install_registers_the_five_professional_tools(tmp_path):
    app = FastAPI()
    install_canonical_product_api(
        app, db_path=str(tmp_path / "product.sqlite3"), auth_required=False
    )

    names = {spec.name for spec in app.state.tool_registry.list_tools()}
    assert {
        CROP_TOOL_NAME,
        IMAGERY_SEARCH_TOOL_NAME,
        IMAGERY_PREPARATION_TOOL_NAME,
        WORKFLOW_REPORT_TOOL_NAME,
        LAI_INVERSION_TOOL_NAME,
    } <= names
    assert (
        app.state.tool_registry.get_definition(LAI_INVERSION_TOOL_NAME).spec.availability
        == "available"
    )
