"""Tests for the local Qwen gateway starter helpers."""

from __future__ import annotations

import os
from pathlib import Path

from scripts.start_gateway_qwen_local import (
    build_runtime_paths,
    configure_demo_environment,
)


def test_build_runtime_paths_creates_expected_layout(tmp_path: Path) -> None:
    paths = build_runtime_paths(str(tmp_path))

    assert paths["root"] == str(tmp_path.resolve())
    assert paths["database_path"].endswith("registry.db")
    assert paths["vectorstore_dir"].endswith("rag_store")
    assert paths["report_output_dir"].endswith("reports")
    assert paths["mask_output_dir"].endswith("masks")
    assert paths["visualization_output_dir"].endswith("visualizations")


def test_configure_demo_environment_sets_runtime_env(tmp_path: Path) -> None:
    previous_env = dict(os.environ)
    try:
        paths = configure_demo_environment(
            base_dir=str(tmp_path),
            port=19090,
            model_path="/models/qwen",
            runtime_python="/opt/anaconda3/bin/python",
            cuda_visible_devices="0,6",
        )

        assert Path(paths["root"]).exists()
        assert os.environ["DATABASE_URL"] == f"sqlite:///{paths['database_path']}"
        assert os.environ["ORCHESTRATOR_DATABASE_URL"] == f"sqlite:///{paths['database_path']}"
        assert os.environ["APP_PORT"] == "19090"
        assert os.environ["VECTORSTORE_DIR"] == paths["vectorstore_dir"]
        assert os.environ["AGENT_LLM_BACKEND"] == "subprocess_qwen"
        assert os.environ["AGENT_LLM_MODEL_PATH"] == "/models/qwen"
        assert os.environ["AGENT_LLM_RUNTIME_PYTHON"] == "/opt/anaconda3/bin/python"
        assert os.environ["AGENT_LLM_CUDA_VISIBLE_DEVICES"] == "0,6"
    finally:
        os.environ.clear()
        os.environ.update(previous_env)
