"""Optional LLM-backed result summarization for the executor role."""

from __future__ import annotations

import json
import logging

from pydantic import Field

from infra.llm.provider import AgentLLMError, AgentLLMProvider
from shared.schemas.common import BaseSchema
from shared.schemas.executor import ExecutorTaskInput, ExecutorTaskOutput

logger = logging.getLogger(__name__)


class ExecutorMessageSummary(BaseSchema):
    """Structured executor message returned by the shared LLM."""

    message: str = Field(..., description="Short factual summary of the task result.")


class ExecutorReasoner:
    """Enhance executor outputs with a shared LLM-backed message when enabled."""

    def __init__(
        self,
        *,
        llm_provider: AgentLLMProvider | None = None,
        enabled: bool = True,
    ) -> None:
        self._llm_provider = llm_provider
        self._enabled = enabled

    def enhance_result(
        self,
        *,
        task: ExecutorTaskInput,
        result: ExecutorTaskOutput,
        system_prompt: str,
    ) -> ExecutorTaskOutput:
        """Return a result with an optional LLM-authored execution summary."""
        if not self._enabled or self._llm_provider is None:
            return result

        try:
            summary = self._llm_provider.generate_structured(
                system_prompt=system_prompt,
                user_prompt=(
                    "Summarize the executor result in one short factual sentence.\n"
                    "Do not invent fields or change success semantics.\n"
                    f"Task:\n{json.dumps(task.model_dump(), ensure_ascii=True, sort_keys=True)}\n\n"
                    f"Result:\n{json.dumps(result.model_dump(), ensure_ascii=True, sort_keys=True)}"
                ),
                response_model=ExecutorMessageSummary,
            )
        except AgentLLMError as exc:
            logger.warning(
                "executor_reasoner_fallback | request_id=%s | tool_name=%s | detail=%s",
                task.request_id,
                task.tool_name,
                str(exc),
            )
            return result

        return ExecutorTaskOutput(
            request_id=result.request_id,
            tool_name=result.tool_name,
            success=result.success,
            message=summary.message or result.message,
            output=result.output,
        )
