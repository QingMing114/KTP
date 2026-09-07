"""Current canonical product protocol contract tests.

These tests intentionally install ``api.canonical`` directly.  They replace
the retired ``ktp_backend.product_protocol`` import-skip suite so a green run
always exercises the implementation shipped by the product entry point.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.canonical.router import install_canonical_product_api
from v2.runtime.store import InMemoryRuntimeStore


def _build_product_app(tmp_path: Path) -> FastAPI:
    app = FastAPI()
    app.state.runtime_store = InMemoryRuntimeStore()
    install_canonical_product_api(
        app,
        db_path=str(tmp_path / "product.sqlite3"),
        auth_required=True,
        auth_token="product-test-token",
    )
    return app


def _auth() -> dict[str, str]:
    return {"Authorization": "Bearer product-test-token"}


def test_current_canonical_manifest_and_auth_boundary(tmp_path: Path) -> None:
    app = _build_product_app(tmp_path)
    with TestClient(app) as client:
        manifest = client.get("/api/product/v1/manifest")
        unauthorized = client.get("/api/product/v1/datasets")
        authorized = client.get("/api/product/v1/datasets", headers=_auth())

    assert manifest.status_code == 200
    assert manifest.json()["protocol_version"] == "1.1"
    assert manifest.json()["delivery_modes"] == ["async"]
    assert unauthorized.status_code == 401
    assert unauthorized.json()["error"]["code"] == "UNAUTHORIZED"
    assert authorized.status_code == 200


def test_current_canonical_dataset_idempotency_and_pagination(tmp_path: Path) -> None:
    app = _build_product_app(tmp_path)
    source = tmp_path / "scene.tif"
    source.write_bytes(b"scene")
    body = {
        "source": {"kind": "local_path", "uri": str(source)},
        "display_name": "scene.tif",
        "defaults": {"region": "gansu", "crop_type": "maize", "task_type": "lai_inversion"},
    }
    headers = {**_auth(), "Idempotency-Key": "dataset-current-1"}

    with TestClient(app) as client:
        first = client.post("/api/product/v1/datasets", headers=headers, json=body)
        replay = client.post("/api/product/v1/datasets", headers=headers, json=body)
        conflict = client.post(
            "/api/product/v1/datasets",
            headers=headers,
            json={**body, "display_name": "different.tif"},
        )
        listed = client.get("/api/product/v1/datasets?limit=1", headers=_auth())

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json()["dataset_id"] == first.json()["dataset_id"]
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert listed.status_code == 200
    assert listed.json()["items"][0]["defaults"]["crop_type"] == "maize"


def test_current_canonical_conversation_and_error_envelopes(tmp_path: Path) -> None:
    app = _build_product_app(tmp_path)
    with TestClient(app) as client:
        created = client.post(
            "/api/product/v1/conversations",
            headers={**_auth(), "Idempotency-Key": "conversation-current-1"},
            json={"title": "Current contract"},
        )
        invalid = client.post("/api/product/v1/imagery/search", json={"invalid": True})
        missing = client.get("/api/product/v1/not-a-route", headers=_auth())

    assert created.status_code == 201
    assert created.json()["title"] == "Current contract"
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "INVALID_REQUEST"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "INVALID_REQUEST"
