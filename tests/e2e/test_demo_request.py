"""E2E-style test for the local demo request helper."""

from __future__ import annotations

import pytest

from test_support.chat_first_llm import IntegrationChatFirstLLMProvider

try:
    from scripts.demo_end_to_end import run_demo_request
except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
    pytest.skip(f"demo request e2e requires optional dependency: {exc.name}", allow_module_level=True)


def test_demo_request_returns_complete_response(tmp_path) -> None:
    result = run_demo_request(
        base_dir=str(tmp_path),
        llm_provider_override=IntegrationChatFirstLLMProvider(),
    )

    assert result["status"] == "completed"
    assert result["workflow"]["report_result"] is not None
    assert result["workflow"]["confidence_result"] is not None
    assert result["workflow"]["visualization_result"] is not None
    assert result["request_id"] == "req-demo-001"
