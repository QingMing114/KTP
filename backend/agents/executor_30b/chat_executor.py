"""Bounded chat executor for the self-scheduling runtime."""

from __future__ import annotations

import json
import logging

from agents.executor_30b.chat_prompts import CHAT_EXECUTOR_SYSTEM_PROMPT
from infra.llm.provider import AgentLLMError, AgentLLMProvider
from shared.schemas.agent_runtime import ExecutorAction, PlannerDecision, PlannerStep, ToolSpec

logger = logging.getLogger(__name__)


class ChatExecutor:
    """LLM-first bounded step executor with deterministic fallback."""

    def __init__(self, *, llm_provider: AgentLLMProvider | None = None) -> None:
        self._llm_provider = llm_provider

    def choose_action(
        self,
        *,
        planner_decision: PlannerDecision,
        step: PlannerStep | None,
        available_tools: list[ToolSpec],
        conversation_history: str = "",
    ) -> ExecutorAction:
        fallback = self._heuristic_action(
            planner_decision=planner_decision,
            step=step,
            available_tools=available_tools,
        )
        if self._llm_provider is None:
            return fallback

        try:
            action = self._llm_provider.generate_structured(
                system_prompt=CHAT_EXECUTOR_SYSTEM_PROMPT,
                user_prompt=(
                    "Return an executor JSON object for one bounded planner step.\n"
                    "Available tools (JSON):\n"
                    f"{json.dumps([tool.model_dump() for tool in available_tools], ensure_ascii=False, sort_keys=True)}\n\n"
                    "Planner decision (JSON):\n"
                    f"{json.dumps(planner_decision.model_dump(), ensure_ascii=False, sort_keys=True)}\n\n"
                    "Current step (JSON):\n"
                    f"{json.dumps(step.model_dump() if step else {}, ensure_ascii=False, sort_keys=True)}\n\n"
                    "Conversation history:\n"
                    f"{conversation_history or '无'}"
                ),
                response_model=ExecutorAction,
            )
        except AgentLLMError as exc:
            logger.warning("chat_executor_llm_fallback | detail=%s", str(exc))
            return fallback

        tool_names = {tool.name for tool in available_tools}
        if action.decision == "invoke_tool" and action.tool_name not in tool_names:
            return fallback
        return action

    @staticmethod
    def _heuristic_action(
        *,
        planner_decision: PlannerDecision,
        step: PlannerStep | None,
        available_tools: list[ToolSpec],
    ) -> ExecutorAction:
        tool_names = {tool.name for tool in available_tools}
        if planner_decision.route == "direct_answer":
            return ExecutorAction(
                step_id=step.step_id if step else "final",
                decision="return_answer",
                tool_name=None,
                tool_input={},
                message="Planner selected direct_answer; no tool call required.",
            )

        if step is None or step.action != "call_tool" or not step.tool_name:
            return ExecutorAction(
                step_id=step.step_id if step else "unknown",
                decision="request_replan",
                tool_name=None,
                tool_input={},
                message="Planner step is missing or malformed for tool execution.",
            )

        if step.tool_name not in tool_names:
            return ExecutorAction(
                step_id=step.step_id,
                decision="request_replan",
                tool_name=None,
                tool_input={},
                message="Planner selected a tool outside the bounded tool set.",
            )

        return ExecutorAction(
            step_id=step.step_id,
            decision="invoke_tool",
            tool_name=step.tool_name,
            tool_input=step.tool_input,
            message="Invoke the planner-selected bounded tool with validated input.",
        )
