"""Gateway adapter for the bounded self-scheduling chat runtime."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from apps.api_gateway.schemas.chat import ChatRequest
from apps.api_gateway.services.conversation_store import ConversationTurn
from apps.orchestrator.chat_graph.runtime import run_chat_runtime
from apps.orchestrator.chat_graph.states import create_initial_chat_state
from apps.orchestrator.chat_graph.workflow import ChatRuntimeGraphUnavailable, run_chat_runtime_graph

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatRuntimeResult:
    """Normalized gateway-facing result from the bounded chat runtime."""

    success: bool
    response_mode: str
    final_mode: str
    route_reason_suffix: str
    answer: str
    workflow_status: str | None
    rag_result: dict[str, Any] | None
    inference_result: dict[str, Any] | None
    report_result: dict[str, Any] | None
    confidence_result: dict[str, Any] | None
    visualization_result: dict[str, Any] | None
    sources: list[str]
    context: dict[str, Any]
    region: str | None
    crop_type: str | None
    task_type: str | None


class ChatRuntimeAdapter:
    """Run the bounded chat runtime and normalize its output for gateway use."""

    def __init__(self, *, max_replans: int = 1) -> None:
        self._max_replans = max(0, int(max_replans))

    def run(
        self,
        *,
        request_id: str,
        user_id: str,
        conversation_id: str,
        request: ChatRequest,
        history: list[ConversationTurn],
    ) -> ChatRuntimeResult:
        logger.info(
            "chat_runtime_adapter_started | request_id=%s | user_id=%s | conversation_id=%s",
            request_id,
            user_id,
            conversation_id,
        )
        state = create_initial_chat_state(
            request_id=request_id,
            user_id=user_id,
            conversation_id=conversation_id,
            user_message=request.message,
            conversation_history=self._render_history(history),
            region=request.region,
            crop_type=request.crop_type,
            task_type=request.task_type,
            max_replans=self._max_replans,
        )
        runner = "langgraph"
        try:
            final_state = run_chat_runtime_graph(state)
        except ChatRuntimeGraphUnavailable:
            runner = "dry_run_fallback"
            final_state = run_chat_runtime(state)
        result = self._normalize_final_state(final_state)
        result.context["runtime_runner"] = runner
        logger.info(
            "chat_runtime_adapter_succeeded | request_id=%s | final_mode=%s | success=%s | runner=%s",
            request_id,
            result.final_mode,
            result.success,
            runner,
        )
        return result

    @staticmethod
    def _normalize_final_state(final_state: dict[str, Any]) -> ChatRuntimeResult:
        planner_decision = final_state.get("planner_decision") or {}
        observation = final_state.get("tool_observation") or {}
        final_mode = str(final_state.get("final_mode") or "abstain")
        errors = list(final_state.get("errors") or [])
        output = observation.get("output") or {}
        answer = str(final_state.get("final_answer") or "")

        if final_mode == "workflow":
            response_mode = "workflow"
            route_suffix = "chat_graph:workflow"
        elif final_mode == "rag_qa":
            response_mode = "qa"
            route_suffix = "chat_graph:rag_qa"
        elif final_mode == "abstain":
            response_mode = "agent"
            route_suffix = "chat_graph:abstain"
        else:
            response_mode = "agent"
            route_suffix = "chat_graph:direct_answer"

        success = bool(answer) and not errors and (observation.get("success", True) is not False)
        if final_mode == "abstain":
            success = False
        if final_mode == "workflow":
            success = success and output.get("workflow_status") == "completed"

        return ChatRuntimeResult(
            success=success,
            response_mode=response_mode,
            final_mode=final_mode,
            route_reason_suffix=route_suffix,
            answer=answer or "未能生成有效响应。",
            workflow_status=output.get("workflow_status"),
            rag_result=output if final_mode == "rag_qa" else output.get("rag_result"),
            inference_result=output.get("inference_result"),
            report_result=output.get("report_result"),
            confidence_result=output.get("confidence_result"),
            visualization_result=output.get("visualization_result"),
            sources=list(observation.get("sources") or output.get("sources") or []),
            context={
                "chat_runtime_status": final_state.get("status"),
                "runtime_trace": list(final_state.get("runtime_trace") or []),
                "replan_count": int(final_state.get("replan_count", 0) or 0),
                "max_replans": int(final_state.get("max_replans", 1) or 1),
                "planner_decision": planner_decision,
                "tool_observation": observation,
                "errors": errors,
            },
            region=final_state.get("region"),
            crop_type=final_state.get("crop_type"),
            task_type=final_state.get("task_type"),
        )

    @staticmethod
    def _render_history(history: list[ConversationTurn]) -> str:
        if not history:
            return ""
        lines = []
        for index, turn in enumerate(history, start=1):
            lines.append(f"第{index}轮 | 模式：{turn.mode} | 用户：{turn.user_message} | 助手：{turn.answer}")
        return "\n".join(lines)
