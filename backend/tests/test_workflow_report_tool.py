"""Workflow report tool tests (P1-P5).

The report is a pure projection of stored workflow state. The workflow finish
path invokes the tool through the registry; the service is the same code used by
embedded callers without a registry.
"""

from __future__ import annotations

import pytest

from runtime.analysis_workflow_runner import _finish
from runtime.workflow_report import (
    WORKFLOW_REPORT_TOOL_NAME,
    write_workflow_report,
)
from schemas.analysis_workflow import CreateAnalysisWorkflowRequest
from schemas.runtime import ObservationV2
from v2.tools.crop_tool import CROP_TOOL_NAME
from v2.tools.imagery_preparation_tool import IMAGERY_PREPARATION_TOOL_NAME
from v2.tools.imagery_search_tool import IMAGERY_SEARCH_TOOL_NAME
from v2.tools.registry import ToolRegistryV2, ToolUnavailableError
from v2.tools.workflow_report_tool import (
    build_workflow_report_tool_spec,
    register_unavailable_workflow_report_tool,
)

from test_analysis_workflow_api import AOI, SNAPSHOT, _app


def _workflow(tmp_path):
    app = _app(tmp_path / "report.sqlite3")
    store = app.state.analysis_workflow_store
    workflow = store.create(
        CreateAnalysisWorkflowRequest.model_validate(
            {
                "aoi": AOI,
                "imagery_item_id": "S2-report",
                "imagery_snapshot": SNAPSHOT,
                "requested_task_ids": ["potential"],
                "start_immediately": False,
            }
        ),
        owner_id="anonymous",
    )
    store.update_step(
        workflow.workflow_id,
        "crop",
        owner_id="anonymous",
        status="completed",
        result={"predicted_class": {"class_id": 0, "name_zh": "玉米", "score": 0.8}},
    )
    store.update_step(
        workflow.workflow_id,
        "potential",
        owner_id="anonymous",
        status="completed",
        result={"canopy_index": 41.9, "output_type": "uncalibrated_canopy_index"},
    )
    return app, store, workflow.workflow_id


def test_service_writes_the_report_and_links_it(tmp_path):
    app, store, workflow_id = _workflow(tmp_path)
    artifact_root = tmp_path / "artifacts"

    references = write_workflow_report(
        workflows=store,
        workflow_id=workflow_id,
        owner_id="anonymous",
        artifact_root=artifact_root,
        artifacts=app.state.product_artifact_store,
    )

    assert references is not None
    assert references["report_kind"] == "workflow_summary_report"
    assert references["report_uri"].startswith("/api/product/v1/artifacts/")
    updated = store.get(workflow_id, owner_id="anonymous")
    assert updated.report_uri == references["report_uri"]
    assert list((artifact_root / "workflows" / workflow_id / "summary").glob("workflow_summary_report_*.html"))


def test_service_returns_none_for_an_unknown_workflow(tmp_path):
    app, store, _ = _workflow(tmp_path)
    assert (
        write_workflow_report(
            workflows=store,
            workflow_id="missing",
            owner_id="anonymous",
            artifact_root=tmp_path / "artifacts",
            artifacts=app.state.product_artifact_store,
        )
        is None
    )


def test_spec_is_read_only_and_host_invoked():
    spec = build_workflow_report_tool_spec(available=True)

    assert spec.name == WORKFLOW_REPORT_TOOL_NAME
    assert spec.category == "remote_sensing"
    assert spec.surface_visibility == "debug"
    assert spec.safety_level == "safe"
    assert spec.permissions == ["artifact:write"]
    assert spec.produces_artifacts == ["workflow_summary_report"]
    assert spec.presentation is not None
    assert spec.presentation.result_renderer == "workflow_report"
    assert spec.input_schema["additionalProperties"] is False


def test_model_visibility_is_an_explicit_gate():
    assert build_workflow_report_tool_spec(available=True).surface_visibility == "debug"
    assert (
        build_workflow_report_tool_spec(available=True, model_visible=True).surface_visibility
        == "all"
    )


def test_tool_generates_the_report_through_the_registry(tmp_path):
    app, store, workflow_id = _workflow(tmp_path)

    observation, artifacts = app.state.tool_registry.invoke(
        tool_name=WORKFLOW_REPORT_TOOL_NAME,
        tool_input={"run_id": workflow_id, "owner_id": "anonymous"},
    )

    assert observation.status == "success"
    assert observation.payload["report_kind"] == "workflow_summary_report"
    assert artifacts == []
    assert store.get(workflow_id, owner_id="anonymous").report_uri


def test_tool_rejects_an_unknown_workflow(tmp_path):
    app, _store, _workflow_id = _workflow(tmp_path)

    with pytest.raises(RuntimeError, match="was not found"):
        app.state.tool_registry.invoke(
            tool_name=WORKFLOW_REPORT_TOOL_NAME,
            tool_input={"run_id": "missing", "owner_id": "anonymous"},
        )


def test_registry_rejects_an_unconfigured_report_tool():
    registry = ToolRegistryV2(definitions={})
    register_unavailable_workflow_report_tool(registry, reason="no workflow store")

    with pytest.raises(ToolUnavailableError, match="no workflow store"):
        registry.invoke(
            tool_name=WORKFLOW_REPORT_TOOL_NAME,
            tool_input={"run_id": "wf-1", "owner_id": "anonymous"},
        )


def test_finish_uses_the_tool_when_a_registry_is_available(tmp_path):
    app, store, workflow_id = _workflow(tmp_path)
    registry = app.state.tool_registry
    calls: list[dict] = []

    def probe(**_kwargs):
        calls.append(_kwargs)
        return (
            ObservationV2(
                source=WORKFLOW_REPORT_TOOL_NAME,
                status="success",
                summary="probe",
                payload={"run_id": workflow_id},
            ),
            [],
        )

    registry.register(WORKFLOW_REPORT_TOOL_NAME, build_workflow_report_tool_spec(available=True), probe)
    _finish(
        store,
        workflow_id,
        "anonymous",
        artifact_root=tmp_path / "artifacts",
        artifacts=app.state.product_artifact_store,
        tool_registry=registry,
    )

    assert calls and calls[0]["run_id"] == workflow_id


def test_canonical_install_registers_the_four_professional_tools(tmp_path):
    app = _app(tmp_path / "report.sqlite3")

    names = {spec.name for spec in app.state.tool_registry.list_tools()}
    assert {
        CROP_TOOL_NAME,
        IMAGERY_SEARCH_TOOL_NAME,
        IMAGERY_PREPARATION_TOOL_NAME,
        WORKFLOW_REPORT_TOOL_NAME,
    } <= names
    assert (
        app.state.tool_registry.get_definition(WORKFLOW_REPORT_TOOL_NAME).spec.availability
        == "available"
    )
