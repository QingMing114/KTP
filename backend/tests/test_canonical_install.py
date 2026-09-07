from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.canonical.router import install_canonical_product_api
from ktp_backend.runtime_host import install_backend_runtime_host
from v2.runtime.store import InMemoryRuntimeStore
from v2.tools.registry import build_default_tool_registry


def test_canonical_router_installs_independently_on_multiple_apps(tmp_path) -> None:
    first_app = FastAPI()
    second_app = FastAPI()
    install_canonical_product_api(first_app, db_path=str(tmp_path / "first.sqlite3"))
    install_canonical_product_api(second_app, db_path=str(tmp_path / "second.sqlite3"))

    with TestClient(first_app) as first_client, TestClient(second_app) as second_client:
        first = first_client.get("/api/product/v1/manifest")
        second = second_client.get("/api/product/v1/manifest")

    assert first.status_code == 200
    assert second.status_code == 200


def test_canonical_install_is_idempotent_per_app(tmp_path) -> None:
    app = FastAPI()
    first_router = install_canonical_product_api(app, db_path=str(tmp_path / "same-app.sqlite3"))
    route_count = len(app.routes)
    second_router = install_canonical_product_api(app, db_path=str(tmp_path / "ignored.sqlite3"))

    assert second_router is first_router
    assert len(app.routes) == route_count
    with TestClient(app) as client:
        assert client.get("/api/product/v1/manifest").status_code == 200


def test_canonical_store_connections_close_during_app_shutdown(tmp_path) -> None:
    app = FastAPI()
    install_canonical_product_api(app, db_path=str(tmp_path / "lifecycle.sqlite3"))
    connection = app.state.product_idempotency_store._db

    with TestClient(app) as client:
        assert client.get("/api/product/v1/manifest").status_code == 200
        connection.execute("SELECT 1")

    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")


def test_canonical_auth_boundary_and_error_envelope(tmp_path) -> None:
    app = FastAPI()
    app.state.runtime_store = InMemoryRuntimeStore()
    install_canonical_product_api(
        app,
        db_path=str(tmp_path / "auth.sqlite3"),
        auth_required=True,
        auth_token="product-secret",
    )

    with TestClient(app) as client:
        public = client.get("/api/product/v1/farms")
        unauthorized = client.post("/api/product/v1/conversations", json={"title": "private"})
        authorized = client.post(
            "/api/product/v1/conversations",
            headers={"Authorization": "Bearer product-secret"},
            json={"title": "private"},
        )
        invalid = client.post("/api/product/v1/imagery/search", json={"invalid": True})
        missing = client.get(
            "/api/product/v1/not-a-route",
            headers={"Authorization": "Bearer product-secret"},
        )

    assert public.status_code == 200
    assert unauthorized.status_code == 401
    assert unauthorized.json()["error"]["code"] == "UNAUTHORIZED"
    assert authorized.status_code == 201
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "INVALID_REQUEST"
    assert "validation" in invalid.json()["error"]["detail"]
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "INVALID_REQUEST"


def test_runtime_host_is_installed_once_per_application() -> None:
    app = FastAPI()
    host = SimpleNamespace(
        runtime_store=object(),
        tool_registry=build_default_tool_registry(),
        agent_registry=object(),
        policy_registry=object(),
        pack_registry=object(),
        runtime_engine=object(),
        llm_provider=None,
    )

    install_backend_runtime_host(app, host)
    route_count = len(app.routes)
    install_backend_runtime_host(app, host)

    assert app.state.backend_runtime_host is host
    assert len(app.routes) == route_count
    with pytest.raises(RuntimeError, match="already installed"):
        install_backend_runtime_host(app, SimpleNamespace())
