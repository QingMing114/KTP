from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("scripts.start_product_backend", reason="scripts.start_product_backend not yet implemented")

from app.bootstrap import build_app
from scripts.start_product_backend import _ensure_project_root_on_path
from shared.config.paths import project_root, var_path


def test_product_root_builds_gateway_app() -> None:
    app = build_app()
    assert app.title
    assert hasattr(app.state, "query_engine")
    assert hasattr(app.state, "runtime_engine")
    assert hasattr(app.state, "dataset_registry")
    assert hasattr(app.state, "async_run_manager")


def test_project_root_and_var_defaults_stay_inside_product_root() -> None:
    root = project_root()
    assert root == Path(__file__).resolve().parents[1]
    assert var_path("artifacts", "reports").startswith(str(root / "var"))


def test_reference_source_tree_is_present() -> None:
    reference_root = project_root() / "references" / "claude_code_like"
    assert reference_root.exists()
    assert (reference_root / "README.md").exists()


def test_librechat_integration_bundle_is_present() -> None:
    root = project_root()
    assert (root / "integrations" / "librechat" / "librechat.yaml.example").exists()
    assert (root / "integrations" / "librechat" / "windows.env.example").exists()
    assert (root / "integrations" / "librechat" / "README.md").exists()
    assert (root / "integrations" / "open-webui" / "README.md").exists()
    assert (root / "integrations" / "open-webui" / "windows.env.example").exists()
    assert (root / "scripts" / "check_librechat_provider.py").exists()
    assert (root / "scripts" / "check_dataset_async_flow.py").exists()
    assert (root / "scripts" / "check_openai_dataset_chat.py").exists()


def test_start_script_can_resolve_product_root() -> None:
    assert _ensure_project_root_on_path() == project_root()
