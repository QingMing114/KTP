from pathlib import Path

import pytest
from pydantic import ValidationError

from schemas.canonical import CanonicalArtifact, SubmissionResponse, SubmissionSSEEvent
from schemas.runtime import ObservationV2, PackArtifactView, RunEventV2


def test_protocol_status_and_stage_values_are_validated() -> None:
    base = {
        "submission_id": "sub-1",
        "conversation_id": "conversation-1",
        "created_at": "2026-07-20T00:00:00+00:00",
    }
    with pytest.raises(ValidationError):
        SubmissionResponse(**base, status="finished", stage="completed")
    with pytest.raises(ValidationError):
        SubmissionResponse(**base, status="completed", stage="done")


def test_event_and_artifact_kinds_reject_unknown_protocol_values() -> None:
    with pytest.raises(ValidationError):
        SubmissionSSEEvent(
            event="unknown.event",
            submission_id="sub-1",
            timestamp="2026-07-20T00:00:00+00:00",
        )
    with pytest.raises(ValidationError):
        RunEventV2(
            sequence=1,
            event="unknown.event",
            run_id="run-1",
            session_id="session-1",
            detail="",
        )
    with pytest.raises(ValidationError):
        PackArtifactView(pack_name="demo", artifact_type="unknown", title="bad")
    with pytest.raises(ValidationError):
        CanonicalArtifact(
            artifact_id="art-1",
            kind="unknown",
            title="bad",
            view_url="/art-1",
        )


def test_approval_does_not_overload_observation_status() -> None:
    event = RunEventV2(
        sequence=1,
        event="approval_required",
        run_id="run-1",
        session_id="session-1",
        detail="approval required",
        run_status="awaiting_approval",
    )
    assert event.run_status == "awaiting_approval"
    with pytest.raises(ValidationError):
        ObservationV2(source="policy", status="awaiting_approval", summary="wait")


def test_v2_bridge_preserves_runtime_class_identity() -> None:
    from schemas.runtime import RunDetail as RuntimeRunDetail
    from v2.shared.schemas import DEPRECATED_ALIASES, RunDetail as BridgedRunDetail

    assert BridgedRunDetail is RuntimeRunDetail
    assert "RunDetail" in DEPRECATED_ALIASES


def test_canonical_adapter_does_not_depend_on_deprecated_schema_bridge() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    checked = [
        backend_root / "api" / "canonical" / "router.py",
        backend_root / "ktp_backend" / "api.py",
        backend_root / "ktp_backend" / "auth.py",
        backend_root / "ktp_backend" / "gateway_bridge.py",
    ]
    for path in checked:
        assert "v2.shared.schemas" not in path.read_text(encoding="utf-8"), path

    runtime_dir = backend_root / "v2" / "runtime"
    for path in runtime_dir.glob("*.py"):
        assert "v2.shared.schemas" not in path.read_text(encoding="utf-8"), path
