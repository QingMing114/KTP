"""Planner agent facade."""

from __future__ import annotations

import logging

from agents.core_70b.planner import RequestPlanner
from agents.core_70b.prompts import PLANNER_SYSTEM_PROMPT
from infra.llm.provider import AgentLLMProvider, get_agent_llm_provider
from shared.schemas.planner import PlannerResult

logger = logging.getLogger(__name__)


class PlannerAgent:
    """Planner role placeholder with a future-LLM-compatible interface."""

    def __init__(
        self,
        planner: RequestPlanner | None = None,
        *,
        llm_provider: AgentLLMProvider | None = None,
    ) -> None:
        self._planner = planner or RequestPlanner(
            llm_provider=get_agent_llm_provider() if llm_provider is None else llm_provider
        )
        self.system_prompt = PLANNER_SYSTEM_PROMPT

    def create_plan(self, request_id: str, user_query: str) -> PlannerResult:
        """Generate a structured plan from a user query."""
        logger.info("planner_agent_started | request_id=%s", request_id)
        result = self._planner.plan(user_query)
        logger.info(
            "planner_agent_succeeded | request_id=%s | task_type=%s",
            request_id,
            result.task_type,
        )
        return result
