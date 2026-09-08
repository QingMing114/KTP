from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Event

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.canonical.router import build_canonical_router
from runtime.artifact_store import ArtifactStore
from schemas.runtime import RequestContextV2, ResolvedDatasetV2
from v2.runtime.cancellation import RuntimeCancellationError
from v2.runtime.events import RunEventEmitter
from v2.tools.remote_sensing.artifacts import AlgorithmArtifactManager
from v2.tools.remote_sensing.bridge import algorithm_result_to_runtime
from v2.tools.remote_sensing.contract import (
    AlgorithmProgressEvent,
    AlgorithmProvenance,
    AlgorithmRuntimeRecord,
    AlgorithmToolInput,
    AlgorithmToolResult,
    AlgorithmValidation,
    ToolExecutionContext,
)
from v2.tools.remote_sensing.dataset_resolver import AlgorithmDatasetResolver
from v2.tools.remote_sensing.errors import AlgorithmToolExecutionError
from v2.tools.remote_sensing.execution import RuntimeAlgorithmExecutionControl
from v2.tools.remote_sensing.model_runtime import ModelRuntimeManager
from v2.tools.remote_sensing.workspace import AlgorithmWorkspace


def _input(dataset_id: str = "dataset-1") -> AlgorithmToolInput:
    return AlgorithmToolInput(dataset_refs=[{"dataset_id": dataset_id, "role": "primary"}])


def _context(*, permissions: list[str] | None = None) -> ToolExecutionContext:
    return ToolExecutionContext(
        execution_id="exec-1",
        trace_id="trace-1",
        user_id="user-1",
        permissions=permissions if permissions is not None else ["dataset:read", "artifact:write"],
        deadline_at=(datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
    )


def test_dataset_resolver_uses_only_registered_context_files(tmp_path) -> None:
    scene = tmp_path / "scene.tif"
    scene.write_bytes(b"raster")
    request_context = RequestContextV2(datasets=[ResolvedDatasetV2(
        dataset_id="dataset-1",
        display_name="scene",
        local_path=str(scene),
        content_type="image/tiff",
    )])

    resolved = AlgorithmDatasetResolver().resolve(
        _input(),
        request_context,
        _context(),
        allowed_suffixes={".tif", ".tiff"},
        allowed_media_types={"image/tiff"},
        max_bytes=100,
        required_roles={"primary"},
    )

    assert resolved[0].path == scene.resolve()
    assert resolved[0].size_bytes == 6


@pytest.mark.parametrize(
    ("tool_input", "permissions", "code"),
    [
        (_input("missing"), ["dataset:read"], "DATASET_NOT_FOUND"),
        (_input(), [], "DATASET_FORBIDDEN"),
    ],
)
def test_dataset_resolver_normalizes_missing_and_forbidden(tmp_path, tool_input, permissions, code) -> None:
    scene = tmp_path / "scene.tif"
    scene.write_bytes(b"raster")
    request_context = RequestContextV2(datasets=[ResolvedDatasetV2(
        dataset_id="dataset-1", display_name="scene", local_path=str(scene)
    )])

    with pytest.raises(AlgorithmToolExecutionError) as captured:
        AlgorithmDatasetResolver().resolve(tool_input, request_context, _context(permissions=permissions))

    assert captured.value.error.code == code
    assert str(scene) not in captured.value.error.message


def test_workspace_is_cleaned_on_success_failure_and_blocks_escape(tmp_path) -> None:
    with AlgorithmWorkspace(tmp_path) as workspace:
        active_path = workspace.path
        assert active_path is not None and active_path.exists()
        with pytest.raises(ValueError, match="escapes"):
            workspace.resolve_output("../escape.txt")
    assert active_path is not None and not active_path.exists()

    failed_path = None
    with pytest.raises(RuntimeError):
        with AlgorithmWorkspace(tmp_path) as workspace:
            failed_path = workspace.path
            raise RuntimeError("controlled")
    assert failed_path is not None and not failed_path.exists()


def test_progress_is_monotonic_and_cancellation_is_cooperative() -> None:
    emitted = []
    emitter = RunEventEmitter(sink=emitted.append, run_id="run-1", session_id="session-1")
    cancelled = Event()
    control = RuntimeAlgorithmExecutionControl(
        context=_context(), event_emitter=emitter, cancellation_event=cancelled, call_id="call-1"
    )
    control.emit_progress(AlgorithmProgressEvent(
        execution_id="exec-1", stage="running", progress=0.5, message="half"
    ))
    assert emitted[0].event == "tool.progress"
    assert emitted[0].tool_progress["stage"] == "running"
    with pytest.raises(ValueError, match="monotonic"):
        control.emit_progress(AlgorithmProgressEvent(
            execution_id="exec-1", stage="running", progress=0.4
        ))
    cancelled.set()
    with pytest.raises(RuntimeCancellationError):
        control.raise_if_cancelled()


def test_expired_deadline_uses_timeout_taxonomy() -> None:
    context = _context().model_copy(update={
        "deadline_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    })
    control = RuntimeAlgorithmExecutionControl(
        context=context,
        event_emitter=RunEventEmitter(sink=None, run_id="run-1", session_id="session-1"),
        cancellation_event=None,
        call_id="call-1",
    )
    with pytest.raises(AlgorithmToolExecutionError) as captured:
        control.raise_if_cancelled()
    assert captured.value.error.code == "TIMEOUT"


def test_artifact_persists_outside_workspace_without_serializing_host_path(tmp_path) -> None:
    persisted_root = tmp_path / "artifacts"
    with AlgorithmWorkspace(tmp_path / "workspaces") as workspace:
        source = workspace.resolve_output("result.json")
        source.write_text('{"ok":true}', encoding="utf-8")
        artifact = AlgorithmArtifactManager(persisted_root).persist(
            source,
            workspace=workspace.path,
            role="classification",
            runtime_kind="classification_result",
            media_type="application/json",
        )
        persisted_path = artifact._internal_path
    assert persisted_path is not None and persisted_path.is_file()
    assert str(persisted_path) not in artifact.model_dump_json()

    now = datetime.now(UTC).isoformat()
    result = AlgorithmToolResult(
        status="succeeded",
        summary="done",
        artifacts=[artifact],
        provenance=AlgorithmProvenance(
            capability_name="remote_sensing.crop_classification",
            tool_version="1.0.0",
            algorithm_name="probe",
            algorithm_version="1.0.0",
        ),
        validation=AlgorithmValidation(passed=True),
        runtime=AlgorithmRuntimeRecord(
            execution_id="exec-1", trace_id="trace-1", started_at=now, finished_at=now, duration_ms=0
        ),
    )
    _observation, runtime_artifacts = algorithm_result_to_runtime(result)
    assert "internal_path" not in runtime_artifacts[0].model_dump()
    store = ArtifactStore(db_path=str(tmp_path / "artifacts.sqlite3"))
    try:
        artifact_id = store.register("run-1", runtime_artifacts[0])
        record = store.get(artifact_id)
        assert artifact_id == artifact.artifact_id
        assert record is not None
        assert record.content_path == str(persisted_path)
        assert record.checksum == artifact.checksum_sha256
        assert record.provenance["capability_name"] == "remote_sensing.crop_classification"
        assert str(persisted_path) not in str(record.provenance)
        app = FastAPI()
        app.state.product_artifact_store = store
        app.state.product_artifact_root = persisted_root
        app.include_router(build_canonical_router(), prefix="/api/product/v1")
        response = TestClient(app).get(artifact.download_url)
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        assert response.content == b'{"ok":true}'
    finally:
        store.close()


def test_model_runtime_releases_resource_after_failure() -> None:
    manager: ModelRuntimeManager[object] = ModelRuntimeManager()
    resource = object()
    unloaded = []
    with pytest.raises(RuntimeError):
        with manager.lease(
            "model:v1", loader=lambda: resource, unloader=unloaded.append, retain=False
        ) as leased:
            assert leased is resource
            assert manager.active_references("model:v1") == 1
            raise RuntimeError("inference failed")
    assert manager.active_references("model:v1") == 0
    assert unloaded == [resource]
