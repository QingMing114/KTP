"""Unit tests for executor-agent LLM result enhancement."""

from __future__ import annotations

import pytest

from agents.executor_30b.agent import ExecutorAgent
from agents.executor_30b.reasoner import ExecutorReasoner
from infra.llm.config import get_agent_llm_config
from infra.llm.provider import get_agent_llm_provider
from shared.schemas.executor import ExecutorTaskInput, ExecutorTaskOutput


class _DummyToolExecutor:
    def execute(self, task: ExecutorTaskInput) -> ExecutorTaskOutput:
        return ExecutorTaskOutput(
            request_id=task.request_id,
            tool_name=task.tool_name,
            success=True,
            message="Inference completed.",
            output={"mask_uri": "/tmp/demo.png"},
        )


class _FakeLLMProvider:
    def generate_structured(self, *, system_prompt, user_prompt, response_model):
        return response_model(
            message="Executor confirmed the inference result and preserved the tool status."
        )


def test_executor_agent_uses_llm_reasoner_message() -> None:
    agent = ExecutorAgent(
        tool_executor=_DummyToolExecutor(),
        reasoner=ExecutorReasoner(
            llm_provider=_FakeLLMProvider(),
            enabled=True,
        ),
    )

    result = agent.execute(
        ExecutorTaskInput(
            request_id="req-executor-001",
            tool_name="run_inference",
            payload={"task_type": "crop_health_detection"},
        )
    )

    assert result.success is True
    assert result.message == (
        "Executor confirmed the inference result and preserved the tool status."
    )


@pytest.fixture(autouse=True)
def _force_heuristic_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LLM_BACKEND", "heuristic")
    get_agent_llm_config.cache_clear()
    get_agent_llm_provider.cache_clear()
