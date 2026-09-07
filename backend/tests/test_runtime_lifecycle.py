from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.canonical.router import build_canonical_router
from runtime.artifact_store import ArtifactStore
from runtime.submission_store import SubmissionStore


def test_artifact_registration_deduplicates_content_and_tracks_versions(tmp_path) -> None:
    content_path = tmp_path / "report.html"
    content_path.write_text("first version", encoding="utf-8")
    store = ArtifactStore(db_path=str(tmp_path / "artifacts.sqlite3"))
    artifact = SimpleNamespace(
        pack_name="prosail",
        artifact_type="lai_html_report",
        title="LAI report",
        uri=str(content_path),
        content=None,
        provenance={"tool_call_id": "tool-1"},
    )

    first_id = store.register("run-1", artifact)
    assert store.register("run-1", artifact) == first_id
    first = store.get(first_id)
    assert first is not None
    assert first.version == 1
    assert first.checksum is not None
    assert first.size_bytes == len(b"first version")
    assert first.content_type == "text/html"
    assert first.provenance["tool_call_id"] == "tool-1"

    content_path.write_text("second version", encoding="utf-8")
    second_id = store.register("run-1", artifact)
    second = store.get(second_id)
    assert second_id != first_id
    assert second is not None and second.version == 2
    assert store.delete_registration(first_id) is True
    assert content_path.exists(), "metadata deletion must never delete the artifact file"
    store.close()


def test_submission_events_fan_out_replay_and_release_only_expired_queues(tmp_path) -> None:
    async def exercise() -> None:
        db_path = tmp_path / "submissions.sqlite3"
        store = SubmissionStore(db_path=str(db_path), loop=asyncio.get_running_loop())
        created = store.create_submission(conversation_id="conversation-1")
        first_queue = store.subscribe(created.submission_id)
        second_queue = store.subscribe(created.submission_id)
        assert first_queue is not None and second_queue is not None

        store.push_event(created.submission_id, {"event": "submission.accepted", "detail": "accepted"})
        first = await asyncio.wait_for(first_queue.get(), timeout=1)
        second = await asyncio.wait_for(second_queue.get(), timeout=1)
        assert first == second
        assert first["sequence"] == 1

        finished_at = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        store.update_submission(
            created.submission_id,
            status="completed",
            stage="completed",
            completed_at=finished_at,
        )
        store.close_submission(created.submission_id)
        await asyncio.sleep(0)
        assert await asyncio.wait_for(first_queue.get(), timeout=1) is None
        assert store.cleanup_terminal_resources(retention_seconds=60) == 1
        assert created.submission_id not in store._subscribers
        assert [event["sequence"] for event in store.list_events(created.submission_id)] == [1]
        store.close()

        reloaded = SubmissionStore(db_path=str(db_path))
        assert [event["detail"] for event in reloaded.list_events(created.submission_id)] == ["accepted"]
        reloaded.close()

    asyncio.run(exercise())


def test_artifact_registration_deletion_is_explicit_and_keeps_the_file(tmp_path) -> None:
    content_path = tmp_path / "retained.txt"
    content_path.write_text("retain me", encoding="utf-8")
    store = ArtifactStore(db_path=str(tmp_path / "management.sqlite3"))
    artifact_id = store.register(
        "run-1",
        SimpleNamespace(
            pack_name="prosail",
            artifact_type="text_card",
            title="retained",
            uri=str(content_path),
            content=None,
        ),
    )
    app = FastAPI()
    app.state.product_artifact_store = store
    app.include_router(build_canonical_router(), prefix="/api/product/v1")

    response = TestClient(app).delete(f"/api/product/v1/management/artifacts/{artifact_id}")

    assert response.status_code == 204
    assert content_path.exists()
    assert store.get(artifact_id) is None
    store.close()
