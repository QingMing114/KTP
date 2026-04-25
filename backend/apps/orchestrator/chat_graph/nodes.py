"""Nodes for the bounded self-scheduling chat runtime."""

from __future__ import annotations

import logging

from agents.core_70b.chat_planner import ChatPlanner
from agents.executor_30b.chat_executor import ChatExecutor
from apps.orchestrator.chat_graph.service_registry import (
    get_chat_runtime_executor,
    get_chat_runtime_orchestrator_client,
    get_chat_runtime_planner,
    get_chat_runtime_rag_client,
)
from apps.orchestrator.chat_graph.states import ChatRuntimeState
from services.rag_service.client import RAGServiceClientError
from services.tool_registry.registry import select_relevant_tools
from shared.schemas.agent_runtime import (
    ExecutorAction,
    PlannerDecision,
    PlannerStep,
    ToolObservation,
    ToolSpec,
)
from shared.schemas.orchestrator import WorkflowRequest

logger = logging.getLogger(__name__)


def load_tool_registry_node(state: ChatRuntimeState) -> dict[str, object]:
    """Load a bounded set of relevant tools into runtime state."""
    request_id = state["request_id"]
    logger.info("chat_runtime_load_tools_started | request_id=%s", request_id)
    tools = select_relevant_tools(
        user_message=state["user_message"],
        task_type=state.get("task_type"),
    )
    logger.info(
        "chat_runtime_load_tools_succeeded | request_id=%s | tool_count=%s",
        request_id,
        len(tools),
    )
    return {
        "available_tools": [tool.model_dump() for tool in tools],
        "runtime_trace": _append_trace(
            state,
            node="load_tool_registry",
            event="success",
            detail=f"loaded {len(tools)} relevant tools",
        ),
        "status": "tools_loaded",
    }


def planner_node(state: ChatRuntimeState) -> dict[str, object]:
    """Run the bounded 70B planner over the current chat state."""
    request_id = state["request_id"]
    logger.info("chat_runtime_planner_started | request_id=%s", request_id)
    planner: ChatPlanner = get_chat_runtime_planner()
    available_tools = _tool_specs_from_state(state)
    decision = planner.plan(
        user_message=state["user_message"],
        available_tools=available_tools,
        conversation_history=state.get("conversation_history", ""),
        region=state.get("region"),
        crop_type=state.get("crop_type"),
        task_type=state.get("task_type"),
        tool_observation=(
            ToolObservation.model_validate(state["tool_observation"])
            if state.get("tool_observation")
            else None
        ),
        replan_count=int(state.get("replan_count", 0)),
    )
    logger.info(
        "chat_runtime_planner_succeeded | request_id=%s | route=%s | step_count=%s",
        request_id,
        decision.route,
        len(decision.steps),
    )
    return {
        "planner_decision": decision.model_dump(),
        "current_step": decision.steps[0].model_dump() if decision.steps else None,
        "region": decision.region or state.get("region"),
        "crop_type": decision.crop_type or state.get("crop_type"),
        "task_type": decision.task_type or state.get("task_type"),
        "runtime_trace": _append_trace(
            state,
            node="planner",
            event=decision.route,
            detail=decision.reasoning_summary,
        ),
        "status": "planned",
    }


def executor_node(state: ChatRuntimeState) -> dict[str, object]:
    """Run the bounded 30B executor for the current planner step."""
    request_id = state["request_id"]
    logger.info("chat_runtime_executor_started | request_id=%s", request_id)
    decision_payload = state.get("planner_decision")
    if not decision_payload:
        action = ExecutorAction(
            step_id="unknown",
            decision="request_replan",
            tool_name=None,
            tool_input={},
            message="Planner decision missing from runtime state.",
        )
        return {
            "executor_action": action.model_dump(),
            "runtime_trace": _append_trace(
                state,
                node="executor",
                event="failed",
                detail=action.message,
            ),
            "status": "executor_failed",
        }

    planner_decision = PlannerDecision.model_validate(decision_payload)
    step_payload = state.get("current_step")
    current_step = PlannerStep.model_validate(step_payload) if step_payload else None
    if planner_decision.route in {"direct_answer", "abstain"}:
        action = ExecutorAction(
            step_id=current_step.step_id if current_step else "final",
            decision="return_answer",
            tool_name=None,
            tool_input={},
            message="Planner selected a terminal response.",
        )
        return {
            "executor_action": action.model_dump(),
            "runtime_trace": _append_trace(
                state,
                node="executor",
                event="terminal",
                detail="Planner selected a terminal response.",
            ),
            "status": "executor_ready",
        }

    executor: ChatExecutor = get_chat_runtime_executor()
    action = executor.choose_action(
        planner_decision=planner_decision,
        step=current_step,
        available_tools=_tool_specs_from_state(state),
        conversation_history=state.get("conversation_history", ""),
    )
    logger.info(
        "chat_runtime_executor_succeeded | request_id=%s | decision=%s | tool_name=%s",
        request_id,
        action.decision,
        action.tool_name,
    )
    return {
        "executor_action": action.model_dump(),
        "runtime_trace": _append_trace(
            state,
            node="executor",
            event=action.decision,
            detail=action.message,
        ),
        "status": "executor_ready",
    }


def tool_dispatch_node(state: ChatRuntimeState) -> dict[str, object]:
    """Invoke the selected bounded tool and normalize the observation."""
    request_id = state["request_id"]
    logger.info("chat_runtime_tool_dispatch_started | request_id=%s", request_id)
    action_payload = state.get("executor_action")
    if not action_payload:
        message = "Executor action missing from runtime state."
        return {
            "tool_observation": _observation(
                step_id="unknown",
                tool_name="none",
                success=False,
                summary=message,
                output={},
            ),
            "errors": [*state.get("errors", []), message],
            "runtime_trace": _append_trace(
                state,
                node="tool_dispatch",
                event="failed",
                detail=message,
            ),
            "status": "tool_dispatch_failed",
        }

    action = ExecutorAction.model_validate(action_payload)
    if action.decision == "return_answer":
        answer = (state.get("planner_decision") or {}).get("answer")
        return {
            "final_answer": answer,
            "final_mode": "direct_answer",
            "tool_observation": _observation(
                step_id=action.step_id,
                tool_name="direct_answer",
                success=True,
                summary="Direct answer selected; no external tool invoked.",
                output={"answer": answer},
            ),
            "runtime_trace": _append_trace(
                state,
                node="tool_dispatch",
                event="skipped",
                detail="Direct answer returned without tool invocation.",
            ),
            "status": "tool_dispatch_skipped",
        }

    if action.decision == "request_replan" or not action.tool_name:
        return {
            "tool_observation": _observation(
                step_id=action.step_id,
                tool_name=action.tool_name or "none",
                success=False,
                summary=action.message,
                output={},
            ),
            "errors": [*state.get("errors", []), action.message],
            "runtime_trace": _append_trace(
                state,
                node="tool_dispatch",
                event="failed",
                detail=action.message,
            ),
            "status": "tool_dispatch_failed",
        }

    if action.tool_name == "rag_search":
        return _dispatch_rag(request_id=request_id, state=state, action=action)
    if action.tool_name == "run_remote_sensing_workflow":
        return _dispatch_workflow(request_id=request_id, state=state, action=action)

    message = f"Unsupported tool dispatch target: {action.tool_name}"
    return {
        "tool_observation": _observation(
            step_id=action.step_id,
            tool_name=action.tool_name,
            success=False,
            summary=message,
            output={},
        ),
        "errors": [*state.get("errors", []), message],
        "runtime_trace": _append_trace(
            state,
            node="tool_dispatch",
            event="failed",
            detail=message,
        ),
        "status": "tool_dispatch_failed",
    }


def validate_tool_observation_node(state: ChatRuntimeState) -> dict[str, object]:
    """Validate whether the most recent tool output is complete enough to trust."""
    request_id = state["request_id"]
    logger.info("chat_runtime_validate_observation_started | request_id=%s", request_id)
    observation_payload = state.get("tool_observation")
    if not observation_payload:
        message = "Tool observation missing from runtime state."
        return {
            "errors": [*state.get("errors", []), message],
            "runtime_trace": _append_trace(
                state,
                node="validate_observation",
                event="failed",
                detail=message,
            ),
            "status": "tool_validation_failed",
        }

    observation = ToolObservation.model_validate(observation_payload)
    if not observation.success:
        return {
            "runtime_trace": _append_trace(
                state,
                node="validate_observation",
                event="failed",
                detail=observation.summary,
            ),
            "status": state.get("status", "tool_dispatch_failed"),
        }

    validation_error = _tool_output_validation_error(state, observation)
    if validation_error:
        logger.warning(
            "chat_runtime_validate_observation_failed | request_id=%s | tool_name=%s | detail=%s",
            request_id,
            observation.tool_name,
            validation_error,
        )
        updated_observation = observation.model_copy(update={"success": False, "summary": validation_error})
        return {
            "tool_observation": updated_observation.model_dump(),
            "errors": [*state.get("errors", []), validation_error],
            "runtime_trace": _append_trace(
                state,
                node="validate_observation",
                event="failed",
                detail=validation_error,
            ),
            "status": "tool_validation_failed",
        }

    logger.info(
        "chat_runtime_validate_observation_succeeded | request_id=%s | tool_name=%s",
        request_id,
        observation.tool_name,
    )
    return {
        "runtime_trace": _append_trace(
            state,
            node="validate_observation",
            event="success",
            detail=f"{observation.tool_name} output validated",
        ),
        "status": "tool_validated",
    }


def finalize_response_node(state: ChatRuntimeState) -> dict[str, object]:
    """Build the final user-facing answer from direct or tool-backed results."""
    request_id = state["request_id"]
    logger.info("chat_runtime_finalize_started | request_id=%s", request_id)
    final_answer = state.get("final_answer")
    final_mode = state.get("final_mode")

    if final_answer:
        return {
            "final_answer": final_answer,
            "final_mode": final_mode or "direct_answer",
            "runtime_trace": _append_trace(
                state,
                node="finalize_response",
                event="success",
                detail=f"finalized as {final_mode or 'direct_answer'}",
            ),
            "status": "finalized",
        }

    planner_payload = state.get("planner_decision")
    if planner_payload:
        planner_decision = PlannerDecision.model_validate(planner_payload)
        if planner_decision.route == "direct_answer":
            return {
                "final_answer": planner_decision.answer,
                "final_mode": "direct_answer",
                "runtime_trace": _append_trace(
                    state,
                    node="finalize_response",
                    event="success",
                    detail="Finalized from planner direct answer.",
                ),
                "status": "finalized",
            }
        if planner_decision.route == "abstain":
            errors = state.get("errors", [])
            answer = planner_decision.reasoning_summary
            if errors:
                answer = f"{answer}\n\n最近一次错误：{errors[-1]}"
            return {
                "final_answer": answer,
                "final_mode": "abstain",
                "runtime_trace": _append_trace(
                    state,
                    node="finalize_response",
                    event="abstain",
                    detail=answer,
                ),
                "status": "finalized",
            }

    observation_payload = state.get("tool_observation")
    if observation_payload:
        observation = ToolObservation.model_validate(observation_payload)
        if observation.tool_name == "rag_search":
            summary = observation.output.get("summary") or observation.summary
            return {
                "final_answer": str(summary),
                "final_mode": "rag_qa",
                "runtime_trace": _append_trace(
                    state,
                    node="finalize_response",
                    event="success",
                    detail="Finalized from RAG observation.",
                ),
                "status": "finalized",
            }
        if observation.tool_name == "run_remote_sensing_workflow":
            output = observation.output
            parts: list[str] = [observation.summary]
            if output.get("report_result"):
                parts.append("已生成报告结果。")
            if output.get("confidence_result"):
                parts.append("已包含置信度结果。")
            return {
                "final_answer": "\n".join(parts),
                "final_mode": "workflow",
                "runtime_trace": _append_trace(
                    state,
                    node="finalize_response",
                    event="success",
                    detail="Finalized from workflow observation.",
                ),
                "status": "finalized",
            }
        return {
            "final_answer": observation.summary,
            "final_mode": final_mode or "tool_backed_answer",
            "runtime_trace": _append_trace(
                state,
                node="finalize_response",
                event="success",
                detail="Finalized from generic tool observation.",
            ),
            "status": "finalized",
        }

    return {
        "final_answer": "未能生成有效响应。",
        "final_mode": final_mode or "abstain",
        "runtime_trace": _append_trace(
            state,
            node="finalize_response",
            event="failed",
            detail="No final answer could be produced.",
        ),
        "status": "finalized",
    }


def _dispatch_rag(
    *,
    request_id: str,
    state: ChatRuntimeState,
    action: ExecutorAction,
) -> dict[str, object]:
    try:
        result = get_chat_runtime_rag_client().run_rag(
            request_id=request_id,
            user_query=str(action.tool_input.get("user_query") or state["user_message"]),
            task_type=state.get("task_type"),
            region=state.get("region"),
            crop_type=state.get("crop_type"),
            inference_result=None,
            context=action.tool_input.get("context") or {},
            top_k=action.tool_input.get("top_k"),
        )
    except RAGServiceClientError as exc:
        message = str(exc)
        return {
            "tool_observation": _observation(
                step_id=action.step_id,
                tool_name="rag_search",
                success=False,
                summary=message,
                output={},
            ),
            "errors": [*state.get("errors", []), message],
            "runtime_trace": _append_trace(
                state,
                node="tool_dispatch",
                event="failed",
                detail=message,
            ),
            "status": "tool_dispatch_failed",
        }

    return {
        "tool_observation": _observation(
            step_id=action.step_id,
            tool_name="rag_search",
            success=True,
            summary=result.summary,
            output=result.model_dump(),
            sources=result.sources,
        ),
        "final_mode": "rag_qa",
        "runtime_trace": _append_trace(
            state,
            node="tool_dispatch",
            event="success",
            detail="rag_search completed",
        ),
        "status": "tool_completed",
    }


def _dispatch_workflow(
    *,
    request_id: str,
    state: ChatRuntimeState,
    action: ExecutorAction,
) -> dict[str, object]:
    workflow_request = WorkflowRequest(
        request_id=request_id,
        user_query=str(action.tool_input.get("message") or state["user_message"]),
        region=action.tool_input.get("region") or state.get("region"),
        crop_type=action.tool_input.get("crop_type") or state.get("crop_type"),
        task_type=action.tool_input.get("task_type") or state.get("task_type"),
        image_path=action.tool_input.get("image_path"),
        use_mock=action.tool_input.get("use_mock"),
        extra_params=action.tool_input.get("extra_params") or {},
    )
    response = get_chat_runtime_orchestrator_client().run_workflow(workflow_request)
    final_state = response.final_state
    summary = (
        final_state.get("message")
        or final_state.get("response_message")
        or f"Workflow completed with status={response.status}."
    )
    output = {
        "workflow_status": response.status,
        "inference_result": final_state.get("inference_result"),
        "rag_result": final_state.get("rag_result"),
        "report_result": final_state.get("report_result"),
        "confidence_result": final_state.get("confidence_result"),
        "visualization_result": final_state.get("visualization_result"),
        "sources": final_state.get("sources", []),
        "route_reason": final_state.get("route_reason"),
    }
    return {
        "tool_observation": _observation(
            step_id=action.step_id,
            tool_name="run_remote_sensing_workflow",
            success=True,
            summary=str(summary),
            output=output,
            sources=list(final_state.get("sources", [])),
        ),
        "workflow_status": response.status,
        "final_mode": "workflow",
        "runtime_trace": _append_trace(
            state,
            node="tool_dispatch",
            event="success",
            detail=f"workflow completed with status={response.status}",
        ),
        "status": "tool_completed",
    }


def _tool_specs_from_state(state: ChatRuntimeState) -> list[ToolSpec]:
    return [ToolSpec.model_validate(tool) for tool in state.get("available_tools", [])]


def _append_trace(
    state: ChatRuntimeState,
    *,
    node: str,
    event: str,
    detail: str,
) -> list[dict]:
    return [
        *state.get("runtime_trace", []),
        {
            "node": node,
            "event": event,
            "detail": detail,
            "replan_count": int(state.get("replan_count", 0)),
        },
    ]


def _tool_output_validation_error(
    state: ChatRuntimeState,
    observation: ToolObservation,
) -> str | None:
    output = observation.output or {}
    planner_payload = state.get("planner_decision") or {}
    planner_decision = PlannerDecision.model_validate(planner_payload) if planner_payload else None

    if observation.tool_name == "rag_search":
        summary = output.get("summary")
        if not summary:
            return "RAG tool returned no summary."
        return None

    if observation.tool_name == "run_remote_sensing_workflow":
        workflow_status = output.get("workflow_status")
        if workflow_status != "completed":
            return f"Workflow tool returned non-completed status: {workflow_status!r}."
        if planner_decision and planner_decision.need_report and not output.get("report_result"):
            return "Workflow tool did not return the requested report result."
        if planner_decision and planner_decision.need_confidence and not output.get("confidence_result"):
            return "Workflow tool did not return the requested confidence result."
        return None

    return None


def _observation(
    *,
    step_id: str,
    tool_name: str,
    success: bool,
    summary: str,
    output: dict[str, object],
    sources: list[str] | None = None,
) -> dict[str, object]:
    return ToolObservation(
        step_id=step_id,
        tool_name=tool_name,
        success=success,
        summary=summary,
        output=output,
        sources=sources or [],
    ).model_dump()
