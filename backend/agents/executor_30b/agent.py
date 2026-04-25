"""Executor agent facade."""

from __future__ import annotations

import logging

from agents.executor_30b.prompts import EXECUTOR_SYSTEM_PROMPT
from agents.executor_30b.reasoner import ExecutorReasoner
from agents.executor_30b.tool_executor import ToolExecutor
from infra.llm.config import get_agent_llm_config
from infra.llm.provider import get_agent_llm_provider
from shared.schemas.executor import ExecutorTaskInput, ExecutorTaskOutput

logger = logging.getLogger(__name__)


class ExecutorAgent:
    """Executor role placeholder with a replaceable tool-execution boundary."""

    def __init__(
        self,
        tool_executor: ToolExecutor | None = None,
        *,
        reasoner: ExecutorReasoner | None = None,
    ) -> None:
        self._tool_executor = tool_executor or ToolExecutor()
        agent_llm_config = get_agent_llm_config()
        self._reasoner = reasoner or ExecutorReasoner(
            llm_provider=get_agent_llm_provider(),
            enabled=agent_llm_config.executor_enabled,
        )
        self.system_prompt = EXECUTOR_SYSTEM_PROMPT

    def execute(self, task: ExecutorTaskInput) -> ExecutorTaskOutput:
        """Execute a structured task through the tool executor."""
        logger.info(
            "executor_agent_started | request_id=%s | tool_name=%s",
            task.request_id,
            task.tool_name,
        )
        result = self._tool_executor.execute(task)
        result = self._reasoner.enhance_result(
            task=task,
            result=result,
            system_prompt=self.system_prompt,
        )
        logger.info(
            "executor_agent_succeeded | request_id=%s | tool_name=%s",
            task.request_id,
            task.tool_name,
        )
        return result
