"""Unit tests for the planner agent placeholder."""

from __future__ import annotations

import pytest

from agents.core_70b.agent import PlannerAgent
from agents.core_70b.planner import RequestPlanner
from infra.llm.config import get_agent_llm_config
from infra.llm.provider import AgentLLMError, get_agent_llm_provider
from shared.schemas.planner import PlannerResult


class _FakePlannerLLMProvider:
    def generate_structured(self, *, system_prompt, user_prompt, response_model):
        return response_model(
            task_type="assess",
            region="Henan",
            crop_type="WHEAT",
            need_training=False,
            need_rag=False,
            need_report=True,
            need_confidence=True,
            reasoning_summary="LLM produced a broad assessment intent.",
        )


class _BrokenPlannerLLMProvider:
    def generate_structured(self, *, system_prompt, user_prompt, response_model):
        raise AgentLLMError("timed out")


def test_planner_agent_returns_structured_result() -> None:
    get_agent_llm_config.cache_clear()
    get_agent_llm_provider.cache_clear()
    agent = PlannerAgent()

    result = agent.create_plan(
        request_id="req-planner-001",
        user_query="Assess wheat disease in Henan and provide a report with confidence.",
    )

    assert result.task_type == "crop_health_detection"
    assert result.region == "henan"
    assert result.crop_type == "wheat"
    assert result.need_report is True
    assert result.need_confidence is True
    assert result.reasoning_summary


def test_planner_agent_normalizes_llm_result_with_heuristic_fallback() -> None:
    agent = PlannerAgent(
        planner=RequestPlanner(llm_provider=_FakePlannerLLMProvider())
    )

    result = agent.create_plan(
        request_id="req-planner-llm-001",
        user_query="Assess wheat disease in Henan and provide a report with confidence.",
    )

    assert result.task_type == "crop_health_detection"
    assert result.region == "henan"
    assert result.crop_type == "wheat"


def test_planner_agent_falls_back_when_llm_errors() -> None:
    agent = PlannerAgent(
        planner=RequestPlanner(llm_provider=_BrokenPlannerLLMProvider())
    )

    result = agent.create_plan(
        request_id="req-planner-llm-error-001",
        user_query="Assess wheat disease in Henan and provide a report with confidence.",
    )

    assert result.task_type == "crop_health_detection"
    assert result.region == "henan"
    assert result.crop_type == "wheat"


def test_planner_agent_detects_additional_region_aliases() -> None:
    agent = PlannerAgent()

    result = agent.create_plan(
        request_id="req-planner-hebei-001",
        user_query="请分析河北省小麦病害情况，并生成报告。",
    )

    assert result.task_type == "crop_health_detection"
    assert result.region == "hebei"
    assert result.crop_type == "wheat"


@pytest.fixture(autouse=True)
def _force_heuristic_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LLM_BACKEND", "heuristic")
    get_agent_llm_config.cache_clear()
    get_agent_llm_provider.cache_clear()
