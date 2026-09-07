from __future__ import annotations

from runtime.submission_store import SubmissionStore


def test_cancelled_submission_is_terminal_and_rejects_late_completion(tmp_path) -> None:
    store = SubmissionStore(db_path=str(tmp_path / "submissions.sqlite3"))
    created = store.create_submission(conversation_id="conversation-cancel")

    assert store.cancel_submission(created.submission_id) is True
    cancellation_event = store.get_cancellation_event(created.submission_id)
    assert cancellation_event is not None
    assert cancellation_event.is_set()

    cancelled = store.update_submission(
        created.submission_id,
        status="cancelled",
        stage="cancelled",
        completed_at="2026-07-20T00:00:00+00:00",
    )
    late = store.update_submission(
        created.submission_id,
        status="completed",
        stage="completed",
        run_id="late-run",
    )

    assert cancelled is not None
    assert cancelled.status == "cancelled"
    assert cancelled.stage == "cancelled"
    assert late is not None
    assert late.status == "cancelled"
    assert late.stage == "cancelled"
    assert late.run_id is None
    store._db.close()
