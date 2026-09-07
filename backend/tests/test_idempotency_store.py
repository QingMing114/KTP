from __future__ import annotations

import threading

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.canonical.router import build_canonical_router
from runtime.idempotency_store import IdempotencyStore
from v2.runtime.store import InMemoryRuntimeStore


def _conversation_app(db_path) -> tuple[FastAPI, IdempotencyStore, InMemoryRuntimeStore]:
    app = FastAPI()
    runtime_store = InMemoryRuntimeStore()
    idempotency_store = IdempotencyStore(db_path=db_path)
    app.state.runtime_store = runtime_store
    app.state.product_idempotency_store = idempotency_store
    app.include_router(build_canonical_router(), prefix="/api/product/v1")
    return app, idempotency_store, runtime_store


def test_canonical_idempotency_replays_after_store_restart_and_rejects_changed_body(tmp_path) -> None:
    db_path = tmp_path / "idempotency.sqlite3"
    app, first_store, first_runtime = _conversation_app(db_path)
    headers = {"Idempotency-Key": "conversation-once"}

    first = TestClient(app).post(
        "/api/product/v1/conversations",
        headers=headers,
        json={"title": "Original"},
    )
    first_store._db.close()
    restarted_app, restarted_store, restarted_runtime = _conversation_app(db_path)
    restarted_client = TestClient(restarted_app)
    replay = restarted_client.post(
        "/api/product/v1/conversations",
        headers=headers,
        json={"title": "Original"},
    )
    conflict = restarted_client.post(
        "/api/product/v1/conversations",
        headers=headers,
        json={"title": "Changed"},
    )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json() == first.json()
    assert len(first_runtime.list_sessions()) == 1
    assert restarted_runtime.list_sessions() == []
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    restarted_store._db.close()


def test_idempotency_claim_is_atomic_across_store_instances(tmp_path) -> None:
    db_path = tmp_path / "concurrent-idempotency.sqlite3"
    stores = [IdempotencyStore(db_path=db_path), IdempotencyStore(db_path=db_path)]
    barrier = threading.Barrier(2)
    statuses: list[str] = []

    def claim(store: IdempotencyStore) -> None:
        barrier.wait()
        result = store.claim(
            principal="user-1",
            key="same-key",
            endpoint="/datasets",
            request_hash="same-hash",
        )
        statuses.append(result.status)

    threads = [threading.Thread(target=claim, args=(store,)) for store in stores]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(statuses) == ["claimed", "in_progress"]
    for store in stores:
        store._db.close()


def test_concurrent_canonical_requests_create_one_resource(tmp_path) -> None:
    app, store, runtime_store = _conversation_app(tmp_path / "concurrent-api.sqlite3")
    barrier = threading.Barrier(2)
    responses = []

    def submit() -> None:
        barrier.wait()
        responses.append(TestClient(app).post(
            "/api/product/v1/conversations",
            headers={"Idempotency-Key": "concurrent-conversation"},
            json={"title": "Created once"},
        ))

    threads = [threading.Thread(target=submit) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert [response.status_code for response in responses] == [201, 201]
    assert responses[0].json() == responses[1].json()
    assert len(runtime_store.list_sessions()) == 1
    store._db.close()


def test_idempotency_keys_are_scoped_by_principal_and_expire(tmp_path) -> None:
    store = IdempotencyStore(db_path=tmp_path / "scoped-idempotency.sqlite3")
    first = store.claim(principal="alice", key="shared", endpoint="/datasets", request_hash="hash")
    second = store.claim(principal="bob", key="shared", endpoint="/datasets", request_hash="hash")
    store._db.execute("UPDATE product_idempotency SET expires_at=0")
    store._db.commit()

    assert first.status == "claimed"
    assert second.status == "claimed"
    assert store.cleanup_expired() == 2
    store._db.close()
