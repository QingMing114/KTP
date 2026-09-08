"""SubExecutor — lightweight single-agent executor for delegated tasks.

Does NOT manage run lifecycle or SSE. Only executes tools and returns results.
Used by BoundedRuntimeEngine for intra-process delegation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from threading import Event
from typing import TYPE_CHECKING

from schemas.runtime import AgentStepV2, PermissionPolicy, RequestContextV2, RunDetail
from v2.runtime.planner import ChatFirstPlanner
from v2.runtime.cancellation import raise_if_cancelled

if TYPE_CHECKING:
    from infra.llm.provider import AgentLLMProvider
    from v2.runtime.events import RunEventEmitter
    from v2.tools.registry import ToolRegistryV2

logger = logging.getLogger(__name__)

_EXECUTOR_MAX_STEPS = 10
_EXECUTOR_SYSTEM_PROMPT_SUFFIX = """
你是一个专业的遥感物理模型执行智能体（executor_30b）。
你的职责是执行物理计算工具，不做对话、不做文档检索。
只使用你持有的工具，完成后用 reply 返回结果摘要。
"""


@dataclass
class SubExecutionResult:
    success: bool
    summary: str
    artifacts: list = field(default_factory=list)
    tool_invocations: list = field(default_factory=list)


class SubExecutor:
    """Executes a delegated goal using a restricted tool subset."""

    def __init__(
        self,
        tool_registry: "ToolRegistryV2",
        llm_provider: "AgentLLMProvider | None",
        policy: PermissionPolicy,
        cancellation_event: Event | None = None,
        user_id: str | None = None,
    ) -> None:
        self._tool_registry = tool_registry
        self._policy = policy
        self._cancellation_event = cancellation_event
        self._user_id = user_id
        self._planner = ChatFirstPlanner(
            llm_provider=llm_provider,
            system_prompt_suffix=_EXECUTOR_SYSTEM_PROMPT_SUFFIX,
        )
        from v2.policies.guard import PolicyGuard
        from v2.runtime.executor import ToolExecutor

        self._executor = ToolExecutor(
            tool_registry=tool_registry,
            policy_guard=PolicyGuard(),
            pack_registry=None,
        )

    def execute(
        self,
        goal: str,
        request_context: RequestContextV2,
        parent_emitter: "RunEventEmitter",
        parent_run: RunDetail,
    ) -> SubExecutionResult:
        """Execute a delegated goal and return the result.

        Emits tool progress events to parent_emitter so they appear
        in the main SSE stream.
        """
        visible_tools = self._tool_registry.list_tools()
        tool_history: list = []
        artifacts: list = []

        for step_index in range(_EXECUTOR_MAX_STEPS):
            raise_if_cancelled(self._cancellation_event)
            try:
                agent_step: AgentStepV2 = self._planner.plan(
                    message=goal,
                    tool_history=tool_history,
                    visible_tools=visible_tools,
                    request_context=request_context,
                    recent_messages=[],
                    last_task_digest=None,
                )
            except Exception as exc:
                logger.error("SubExecutor planner failed: %s", exc)
                return SubExecutionResult(success=False, summary=f"执行失败：{exc}")

            if agent_step.action in ("reply", "clarify"):
                return SubExecutionResult(
                    success=True,
                    summary=agent_step.response_message or "",
                    artifacts=artifacts,
                    tool_invocations=tool_history,
                )

            if agent_step.action == "fail":
                return SubExecutionResult(
                    success=False,
                    summary=agent_step.response_message or "执行失败",
                )

            if not agent_step.tool_calls:
                return SubExecutionResult(success=False, summary="执行器未返回工具调用")

            for tool_call in agent_step.tool_calls:
                raise_if_cancelled(self._cancellation_event)
                result = self._executor.execute_tool_call(
                    run=parent_run,
                    request_context=request_context,
                    tool_call=tool_call,
                    visible_tools=visible_tools,
                    visible_agents=[],
                    policy=self._policy,
                    event_emitter=parent_emitter,
                    cancellation_event=self._cancellation_event,
                    user_id=self._user_id,
                )
                tool_history.append(result["history_item"])
                if result.get("blocked"):
                    return SubExecutionResult(
                        success=False,
                        summary=str(result.get("final_message") or "委派工具被策略拒绝"),
                        artifacts=artifacts,
                        tool_invocations=tool_history,
                    )
                observation = result.get("observation")
                if getattr(observation, "status", None) == "error":
                    return SubExecutionResult(
                        success=False,
                        summary=str(result.get("final_message") or "委派工具执行失败"),
                        artifacts=artifacts,
                        tool_invocations=tool_history,
                    )
                if result.get("artifacts"):
                    artifacts.extend(result["artifacts"])

        return SubExecutionResult(
            success=False,
            summary=f"执行达到步数上限（{_EXECUTOR_MAX_STEPS}步）",
        )
