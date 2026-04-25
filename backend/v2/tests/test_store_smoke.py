from __future__ import annotations

import asyncio

import httpx

from v2.apps.api.config import V2ApiSettings
from v2.apps.api.main import create_app


def _run_request(
    app,
    method: str,
    path: str,
    payload: dict | None = None,
) -> httpx.Response:
    async def _call() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, json=payload)

    return asyncio.run(_call())


def test_v2_sqlite_store_persists_sessions_and_runs(tmp_path) -> None:
    sqlite_path = tmp_path / "runtime.sqlite3"
    settings = V2ApiSettings(store_backend="sqlite", sqlite_path=str(sqlite_path))

    app_one = create_app(settings_override=settings)
    session_response = _run_request(app_one, "POST", "/v2/sessions", {"title": "Persistent Session"})
    session_id = session_response.json()["session"]["session_id"]

    run_response = _run_request(
        app_one,
        "POST",
        f"/v2/sessions/{session_id}/messages",
        {"message": "please use the demo tool and show an artifact"},
    )
    run_id = run_response.json()["run_id"]

    app_two = create_app(settings_override=settings)

    persisted_session = _run_request(app_two, "GET", f"/v2/sessions/{session_id}")
    assert persisted_session.status_code == 200
    assert persisted_session.json()["session_id"] == session_id

    persisted_runs = _run_request(app_two, "GET", f"/v2/sessions/{session_id}/runs")
    assert persisted_runs.status_code == 200
    assert len(persisted_runs.json()) == 1
    assert persisted_runs.json()[0]["run_id"] == run_id

    persisted_all_runs = _run_request(app_two, "GET", "/v2/runs")
    assert persisted_all_runs.status_code == 200
    assert len(persisted_all_runs.json()) == 1
    assert persisted_all_runs.json()[0]["run_id"] == run_id

    persisted_run = _run_request(app_two, "GET", f"/v2/runs/{run_id}")
    assert persisted_run.status_code == 200
    assert persisted_run.json()["run_id"] == run_id

    replay_response = _run_request(app_two, "POST", f"/v2/runs/{run_id}/replay")
    assert replay_response.status_code == 200
    assert replay_response.json()["comparison"]["overall_match"] is True
    assert replay_response.json()["comparison"]["mismatch_fields"] == []

    persisted_runs_after_replay = _run_request(app_two, "GET", f"/v2/sessions/{session_id}/runs")
    assert persisted_runs_after_replay.status_code == 200
    assert len(persisted_runs_after_replay.json()) == 1
