from __future__ import annotations

import logging
import asyncio
import json
from pathlib import Path
from queue import SimpleQueue
from threading import Thread
from typing import Callable, Iterator
from uuid import uuid4

from infra.llm.config import get_agent_llm_config
from infra.llm.provider import AgentLLMError, AgentLLMProvider
from shared.request_normalization import (
    detect_crop_type_from_text,
    detect_region_from_text,
    detect_task_type_from_text,
    extract_image_path_from_text,
)
from v2.adapters.python_services.ktp_services import KTP_DEFAULT_CROP_TYPE, KTP_DEFAULT_REGION, KTP_DEFAULT_TASK_TYPE, KtpExecutionContext, KtpServiceError
from v2.agents.registry import AgentProfileRegistry
from v2.packs.registry import DomainPackRegistry
from v2.policies.guard import PolicyGuard, PolicyGuardError
from v2.policies.registry import PolicyRegistryV2
from v2.runtime.planner import ChatFirstPlanner
from v2.runtime.store import RuntimeStore
from v2.shared.schemas import (
    AgentStepV2,
    AttachmentV2,
    AssistantMessagePartV2,
    AssistantMessageV2,
    DelegationResult,
    ExecutorActionV2,
    ObservationV2,
    PackArtifactView,
    ReplayComparisonV2,
    ReplayResponseV2,
    RequestContextV2,
    RunEventV2,
    RunDetail,
    RunStateV2,
    SessionMessage,
    ToolInvocationView,
    TraceEventV2,
)
from v2.tools.handlers import (
    _artifact_from_confidence,
    _artifact_from_inference,
    _artifact_from_model_lookup,
    _artifact_from_report,
    _artifact_from_visualization,
    _context_payload,
)
from v2.tools.registry import ToolRegistryV2

logger = logging.getLogger(__name__)


def _run_async_or_sync(coro):
    try:
        asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        return asyncio.run(coro)


class BoundedRuntimeEngine:
    """Bounded runtime engine for the V2 KTP single-agent flow."""

    def __init__(
        self,
        *,
        store: RuntimeStore,
        tool_registry: ToolRegistryV2,
        policy_registry: PolicyRegistryV2,
        agent_registry: AgentProfileRegistry,
        pack_registry: DomainPackRegistry,
        llm_provider: AgentLLMProvider | None = None,
    ) -> None:
        self._store = store
        self._tool_registry = tool_registry
        self._policy_registry = policy_registry
        self._agent_registry = agent_registry
        self._pack_registry = pack_registry
        self._llm_provider = llm_provider
        self._planner = ChatFirstPlanner(llm_provider=llm_provider)
        self._guard = PolicyGuard()
        self._llm_config = get_agent_llm_config()

    def run(
        self,
        *,
        session_id: str,
        user_message: str,
        user_id: str | None,
        request_context: RequestContextV2 | None = None,
    ) -> RunDetail:
        run: RunDetail | None = None
        for event in self.stream(
            session_id=session_id,
            user_message=user_message,
            user_id=user_id,
            request_context=request_context,
        ):
            if event.run is not None:
                run = event.run
        if run is None:
            raise RuntimeError("runtime_stream_completed_without_final_run")
        return run

    def stream(
        self,
        *,
        session_id: str,
        user_message: str,
        user_id: str | None,
        request_context: RequestContextV2 | None = None,
    ) -> Iterator[RunEventV2]:
        del user_id  # reserved for future actor-aware policy decisions
        session = self._store.get_session(session_id)
        if session is None:
            raise KeyError(session_id)
        logger.info("v2_runtime_started | session_id=%s", session_id)

        event_queue: SimpleQueue[RunEventV2 | object] = SimpleQueue()
        done_marker = object()
        final_result: dict[str, object] = {}

        def worker() -> None:
            try:
                final_result["run"] = self._run_internal(
                    session_id=session_id,
                    user_message=user_message,
                    request_context=request_context,
                    persist_messages=True,
                    persist_run=True,
                    replay_of_run_id=None,
                    event_sink=event_queue.put,
                )
            except Exception as exc:  # pragma: no cover - forwarded after the queue drains
                final_result["error"] = exc
            finally:
                event_queue.put(done_marker)

        worker_thread = Thread(target=worker, daemon=True)
        worker_thread.start()

        while True:
            item = event_queue.get()
            if item is done_marker:
                break
            if not isinstance(item, RunEventV2):
                logger.warning("v2_runtime_unexpected_event_type | type=%s", type(item).__name__)
                continue
            yield item

        worker_thread.join()

        error = final_result.get("error")
        if isinstance(error, Exception):
            raise error

        run = final_result.get("run")
        if not isinstance(run, RunDetail):
            raise RuntimeError("runtime_stream_completed_without_final_run")

        logger.info(
            "v2_runtime_succeeded | session_id=%s | run_id=%s | status=%s",
            session_id,
            run.run_id,
            run.status,
        )

    def replay(self, *, run_id: str) -> ReplayResponseV2:
        original_run = self._store.get_run(run_id)
        if original_run is None:
            raise KeyError(run_id)

        replayed_run = self._execute(
            session_id=original_run.session_id,
            user_message=original_run.input_message,
            request_context=original_run.input_context,
            persist_messages=False,
            persist_run=False,
            replay_of_run_id=run_id,
        )
        original_state = self._build_run_state(original_run)
        replayed_state = self._build_run_state(replayed_run)
        comparison = self._compare_runs(original_run=original_run, replayed_run=replayed_run)
        return ReplayResponseV2(
            replay_mode="deterministic_dry_replay",
            notes=(
                "Replay re-executes the current bounded runtime deterministically without mutating session "
                "messages or persisting a new run."
            ),
            original_state=original_state,
            replayed_state=replayed_state,
            comparison=comparison,
        )

    def build_run_state(self, *, run_id: str) -> RunStateV2:
        run = self._store.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        return self._build_run_state(run)

    def _run_internal(
        self,
        *,
        session_id: str,
        user_message: str,
        request_context: RequestContextV2 | None,
        persist_messages: bool,
        persist_run: bool,
        replay_of_run_id: str | None,
        event_sink: Callable[[RunEventV2], None] | None,
    ) -> RunDetail:
        session = self._store.get_session(session_id)
        if session is None:
            raise KeyError(session_id)
        run = self._execute(
            session_id=session_id,
            user_message=user_message,
            request_context=request_context,
            persist_messages=persist_messages,
            persist_run=persist_run,
            replay_of_run_id=replay_of_run_id,
            event_sink=event_sink,
        )
        if persist_run:
            session = self._store.get_session(session_id)
            if session is None:
                raise KeyError(session_id)
            session.latest_run_id = run.run_id
            self._store.save_session(session)
        return run

    def _execute(
        self,
        *,
        session_id: str,
        user_message: str,
        request_context: RequestContextV2 | None,
        persist_messages: bool,
        persist_run: bool,
        replay_of_run_id: str | None,
        event_sink: Callable[[RunEventV2], None] | None = None,
    ) -> RunDetail:
        session = self._store.get_session(session_id)
        if session is None:
            raise KeyError(session_id)

        resolved_context = self._resolve_request_context(
            request_context=request_context,
            user_message=user_message,
        )
        policy = self._policy_registry.get_default_policy()
        visible_tools = self._resolve_visible_tools(request_context=resolved_context)
        visible_agents = self._agent_registry.list_profiles()
        previous_latest_run = self._store.get_run(session.latest_run_id) if session.latest_run_id else None

        user_entry = SessionMessage(role="user", content=user_message)
        if persist_messages:
            self._store.append_message(session_id, user_entry)

        run = RunDetail(
            run_id=str(uuid4()),
            session_id=session_id,
            status="completed",
            input_message=user_message,
            input_context=resolved_context,
            output_message="",
            assistant_message=AssistantMessageV2(parts=[]),
            replay_of_run_id=replay_of_run_id,
            trace=[
                TraceEventV2(node="runtime", event="run_created", detail="Created chat-first runtime run."),
                TraceEventV2(
                    node="runtime",
                    event="visibility_loaded",
                    detail=(
                        f"Loaded {len(visible_tools)} tools, {len(visible_agents)} agents, "
                        f"{len(self._pack_registry.list_packs())} packs."
                    ),
                ),
                TraceEventV2(
                    node="runtime",
                    event="request_context_loaded",
                    detail=(
                        f"Entrypoint={resolved_context.entrypoint}, region={resolved_context.region or 'default'}, "
                        f"crop_type={resolved_context.crop_type or 'default'}, task_type={resolved_context.task_type or 'default'}."
                    ),
                ),
            ],
        )
        event_sequence = 0

        def emit_event(
            *,
            event: str,
            detail: str,
            message: SessionMessage | None = None,
            planner_decision=None,
            executor_action=None,
            observation: ObservationV2 | None = None,
            delegation: DelegationResult | None = None,
            tool_invocation: ToolInvocationView | None = None,
            artifact=None,
            output_message: str | None = None,
            run_status: str | None = None,
            include_run: bool = False,
        ) -> None:
            nonlocal event_sequence
            if event_sink is None:
                return
            event_sequence += 1
            event_sink(
                RunEventV2(
                    sequence=event_sequence,
                    event=event,
                    run_id=run.run_id,
                    session_id=session_id,
                    detail=detail,
                    message=message,
                    planner_decision=planner_decision,
                    executor_action=executor_action,
                    observation=observation,
                    delegation=delegation,
                    tool_invocation=tool_invocation,
                    artifact=artifact,
                    assistant_part=(
                        AssistantMessagePartV2(type="text", text=output_message)
                        if event == "assistant.delta" and output_message is not None
                        else None
                    ),
                    assistant_message=run.assistant_message,
                    output_message=output_message,
                    run_status=run_status,
                    run=run if include_run else None,
                )
            )

        emit_event(
            event="run.started",
            detail="Created bounded runtime run and loaded request visibility.",
            message=user_entry,
        )
        emit_event(
            event="assistant.status",
            detail=(
                f"Planning agent loop for entrypoint={resolved_context.entrypoint} with "
                f"{len(visible_tools)} visible tools."
            ),
        )
        tool_history: list[dict[str, object]] = []
        self._execute_agent_loop(
            run=run,
            session_id=session_id,
            user_message=user_message,
            request_context=resolved_context,
            visible_tools=visible_tools,
            visible_agents=visible_agents,
            policy=policy,
            persist_messages=persist_messages,
            previous_latest_run=previous_latest_run,
            tool_history=tool_history,
            emit_event=emit_event,
        )

        if persist_run:
            self._store.save_run(run)
        return run

    def _execute_agent_loop(
        self,
        *,
        run: RunDetail,
        session_id: str,
        user_message: str,
        request_context: RequestContextV2,
        visible_tools,
        visible_agents,
        policy,
        persist_messages: bool,
        previous_latest_run: RunDetail | None,
        tool_history: list[dict[str, object]],
        emit_event: Callable[..., None],
    ) -> None:
        max_steps = min(
            self._llm_config.agent_max_steps if hasattr(self._llm_config, 'agent_max_steps') else 20,
            30,
        )
        session = self._store.get_session(session_id)
        if session is None:
            raise KeyError(session_id)
        recent_messages = list(session.messages)
        last_task_digest = self._build_last_task_digest(previous_latest_run)
        consecutive_replan_count = 0
        last_tool_call_signature: str | None = None
        invalid_image_path_message = self._build_invalid_image_path_clarification(
            user_message=user_message,
            request_context=request_context,
        )
        if invalid_image_path_message is not None:
            clarification_step = AgentStepV2(
                action="clarify",
                reasoning="Real analysis requests require an existing local image path before tool execution.",
                response_message=invalid_image_path_message,
                tool_calls=[],
            )
            run.agent_steps.append(clarification_step)
            run.planner_decision = clarification_step
            run.observation = ObservationV2(
                source="agent.planner",
                status="success",
                summary=invalid_image_path_message,
                payload={
                    "reason": "invalid_image_path",
                    "image_path": request_context.image_path,
                },
            )
            run.trace.append(
                TraceEventV2(
                    node="planner",
                    event="analysis_input_clarification",
                    detail="Abstained before tool execution because the supplied local image path does not exist.",
                )
            )
            self._append_assistant_part(
                run,
                AssistantMessagePartV2(
                    type="status",
                    text=invalid_image_path_message,
                    status="clarify",
                ),
            )
            self._finalize_run(
                run=run,
                session_id=session_id,
                persist_messages=persist_messages,
                message=invalid_image_path_message,
                status="completed",
                replan_count=0,
                delegation_count=0,
                trace_event="run_finalized",
                trace_detail="Run finalized after validating that the requested image path does not exist.",
            )
            emit_event(
                event="assistant.delta",
                detail="Emitted the clarification response for the invalid local image path.",
                output_message=invalid_image_path_message,
                run_status="completed",
            )
            emit_event(
                event="run.completed",
                detail="Run completed with a clarification because the requested local image path does not exist.",
                observation=run.observation,
                output_message=invalid_image_path_message,
                run_status="completed",
                include_run=True,
            )
            return

        for step_index in range(max_steps):
            if step_index == 0 and self._llm_decide_use_direct_reply(
                user_message=user_message,
                request_context=request_context,
                recent_messages=recent_messages,
            ):
                try:
                    response_message = self._generate_direct_chat_reply(
                        user_message=user_message,
                        request_context=request_context,
                        recent_messages=recent_messages,
                        last_task_digest=last_task_digest,
                        session_id=session_id,
                    )
                except AgentLLMError as exc:
                    failure_message = self._describe_llm_failure(
                        exc,
                        phase="direct_reply",
                    )
                    self._append_assistant_part(
                        run,
                        AssistantMessagePartV2(type="error", text=failure_message, status="failed"),
                    )
                    self._append_llm_error_trace(run=run, error=exc, phase="direct_reply")
                    run.trace.append(
                        TraceEventV2(
                            node="planner",
                            event="direct_reply_failed",
                            detail=failure_message,
                        )
                    )
                    run.observation = ObservationV2(
                        source="agent.direct_reply",
                        status="error",
                        summary=failure_message,
                        payload=self._build_llm_error_payload(exc, step_index=step_index),
                    )
                    self._finalize_run(
                        run=run,
                        session_id=session_id,
                        persist_messages=persist_messages,
                        message=failure_message,
                        status="failed",
                        replan_count=0,
                        delegation_count=0,
                        trace_event="run_failed",
                        trace_detail="Run failed because the direct reply path could not obtain a usable LLM answer.",
                    )
                    emit_event(
                        event="run.failed",
                        detail="Run failed because the direct reply path could not obtain a usable LLM answer.",
                        observation=run.observation,
                        output_message=run.output_message,
                        run_status="failed",
                        include_run=True,
                    )
                    return

                run.trace.append(
                    TraceEventV2(
                        node="planner",
                        event="direct_reply_selected",
                        detail="LLM router decided direct-reply path for this request.",
                    )
                )
                direct_step = AgentStepV2(
                    action="reply",
                    reasoning="LLM router decided this is a general chat request, answered through the direct-reply path.",
                    response_message=response_message,
                    tool_calls=[],
                )
                run.agent_steps.append(direct_step)
                run.planner_decision = direct_step
                self._append_assistant_part(
                    run,
                    AssistantMessagePartV2(type="text", text=response_message, status="reply"),
                )
                self._finalize_run(
                    run=run,
                    session_id=session_id,
                    persist_messages=persist_messages,
                    message=response_message,
                    status="completed",
                    replan_count=0,
                    delegation_count=0,
                    trace_event="run_finalized",
                    trace_detail="Run finalized after the direct-reply path selected by LLM router.",
                )
                emit_event(
                    event="assistant.delta",
                    detail="Emitted the final assistant response.",
                    output_message=response_message,
                    run_status="completed",
                )
                emit_event(
                    event="run.completed",
                    detail="Run finalized after the direct-reply path selected by LLM router.",
                    output_message=response_message,
                    run_status="completed",
                    include_run=True,
                )
                return

            try:
                agent_step = self._planner.plan(
                    message=user_message,
                    visible_tools=visible_tools,
                    request_context=request_context,
                    recent_messages=recent_messages,
                    tool_history=tool_history,
                    last_task_digest=last_task_digest,
                )
            except AgentLLMError as exc:
                failure_message = self._describe_llm_failure(
                    exc,
                    phase="structured_planner",
                )
                self._append_assistant_part(
                    run,
                    AssistantMessagePartV2(type="error", text=failure_message, status="failed"),
                )
                self._append_llm_error_trace(run=run, error=exc, phase="structured_planner")
                run.trace.append(
                    TraceEventV2(
                        node="planner",
                        event="planning_failed",
                        detail=failure_message,
                    )
                )
                run.observation = ObservationV2(
                    source="agent.planner",
                    status="error",
                    summary=failure_message,
                    payload=self._build_llm_error_payload(exc, step_index=step_index),
                )
                self._finalize_run(
                    run=run,
                    session_id=session_id,
                    persist_messages=persist_messages,
                    message=failure_message,
                    status="failed",
                    replan_count=0,
                    delegation_count=0,
                    trace_event="run_failed",
                    trace_detail="Run failed because the chat-first planner could not obtain a valid LLM step.",
                )
                emit_event(
                    event="run.failed",
                    detail="Run failed because the chat-first planner could not obtain a valid LLM step.",
                    observation=run.observation,
                    output_message=run.output_message,
                    run_status="failed",
                    include_run=True,
                )
                return

            run.agent_steps.append(agent_step)
            run.planner_decision = agent_step

            emit_event(
                event="thinking",
                detail=agent_step.reasoning or f"选择动作: {agent_step.action}",
            )

            if self._consume_llm_call_metadata().get("schema_alias_applied"):
                run.trace.append(
                    TraceEventV2(
                        node="llm",
                        event="llm_schema_alias_applied",
                        detail="Accepted upstream structured output by mapping content to response_message.",
                    )
                )
            run.trace.append(
                TraceEventV2(
                    node="planner",
                    event="agent_step_selected",
                    detail=f"Agent step {step_index + 1} selected action={agent_step.action}.",
                )
            )
            emit_event(
                event="planner.delta",
                detail=f"Planner reasoning: {agent_step.reasoning[:200] if agent_step.reasoning else 'No reasoning provided'}",
                planner_decision=agent_step,
            )

            if agent_step.action in {"reply", "clarify"}:
                response_message = (agent_step.response_message or "").strip()
                if not response_message:
                    response_message = "The assistant returned an empty reply."
                part_type = "status" if agent_step.action == "clarify" else "text"
                self._append_assistant_part(
                    run,
                    AssistantMessagePartV2(type=part_type, text=response_message, status=agent_step.action),
                )
                self._finalize_run(
                    run=run,
                    session_id=session_id,
                    persist_messages=persist_messages,
                    message=response_message,
                    status="completed",
                    replan_count=0,
                    delegation_count=0,
                    trace_event="run_finalized",
                    trace_detail=f"Run finalized after agent selected {agent_step.action}.",
                )
                emit_event(
                    event="assistant.delta",
                    detail="Emitted the final assistant response.",
                    output_message=response_message,
                    run_status="completed",
                )
                emit_event(
                    event="run.completed",
                    detail=f"Run finalized after agent selected {agent_step.action}.",
                    output_message=response_message,
                    run_status="completed",
                    include_run=True,
                )
                return

            if agent_step.action == "fail":
                failure_message = (agent_step.response_message or "Agent reported an unrecoverable failure.").strip()
                self._append_assistant_part(
                    run,
                    AssistantMessagePartV2(type="error", text=failure_message, status="failed"),
                )
                run.observation = ObservationV2(
                    source="agent.planner",
                    status="error",
                    summary=failure_message,
                    payload={"step_index": step_index},
                )
                self._finalize_run(
                    run=run,
                    session_id=session_id,
                    persist_messages=persist_messages,
                    message=failure_message,
                    status="failed",
                    replan_count=0,
                    delegation_count=0,
                    trace_event="run_failed",
                    trace_detail="Run failed because the planner explicitly returned fail.",
                )
                emit_event(
                    event="run.failed",
                    detail="Run failed because the planner explicitly returned fail.",
                    observation=run.observation,
                    output_message=failure_message,
                    run_status="failed",
                    include_run=True,
                )
                return

            if not agent_step.tool_calls:
                failure_message = "Planner selected call_tools but returned no tool calls."
                self._append_assistant_part(
                    run,
                    AssistantMessagePartV2(type="error", text=failure_message, status="failed"),
                )
                run.observation = ObservationV2(
                    source="agent.planner",
                    status="error",
                    summary=failure_message,
                    payload={"step_index": step_index},
                )
                self._finalize_run(
                    run=run,
                    session_id=session_id,
                    persist_messages=persist_messages,
                    message=failure_message,
                    status="failed",
                    replan_count=0,
                    delegation_count=0,
                    trace_event="run_failed",
                    trace_detail=failure_message,
                )
                emit_event(
                    event="run.failed",
                    detail=failure_message,
                    observation=run.observation,
                    output_message=failure_message,
                    run_status="failed",
                    include_run=True,
                )
                return

            for tool_call in agent_step.tool_calls:
                tool_result = self._execute_single_tool_call(
                    run=run,
                    request_context=request_context,
                    tool_call=tool_call,
                    visible_tools=visible_tools,
                    visible_agents=visible_agents,
                    policy=policy,
                    emit_event=emit_event,
                )
                tool_history.append(tool_result["history_item"])
                run.observation = tool_result["observation"]
                recent_messages = list(self._store.get_session(session_id).messages) if persist_messages else recent_messages
                last_task_digest = self._build_current_task_digest(run)
                if tool_result["blocked"]:
                    failure_message = tool_result["final_message"]
                    self._append_assistant_part(
                        run,
                        AssistantMessagePartV2(type="error", text=failure_message, status="approval_required"),
                    )
                    self._finalize_run(
                        run=run,
                        session_id=session_id,
                        persist_messages=persist_messages,
                        message=failure_message,
                        status="failed",
                        replan_count=0,
                        delegation_count=0,
                        trace_event="run_failed",
                        trace_detail="Run failed because a requested tool requires approval.",
                    )
                    emit_event(
                        event="run.failed",
                        detail="Run failed because a requested tool requires approval.",
                        observation=run.observation,
                        output_message=failure_message,
                        run_status="failed",
                        include_run=True,
                    )
                    return
                if tool_result["observation"].status == "error":
                    failure_message = tool_result["final_message"]
                    self._append_assistant_part(
                        run,
                        AssistantMessagePartV2(type="error", text=failure_message, status="failed"),
                    )
                    self._finalize_run(
                        run=run,
                        session_id=session_id,
                        persist_messages=persist_messages,
                        message=failure_message,
                        status="failed",
                        replan_count=0,
                        delegation_count=0,
                        trace_event="run_failed",
                        trace_detail="Run failed during tool execution.",
                    )
                    emit_event(
                        event="run.failed",
                        detail="Run failed during tool execution.",
                        observation=run.observation,
                        output_message=failure_message,
                        run_status="failed",
                        include_run=True,
                    )
                    return

            current_call_signature = "|".join(
                f"{tc.tool_name}:{json.dumps(tc.tool_input, sort_keys=True, default=str)}"
                for tc in agent_step.tool_calls
            )
            if current_call_signature == last_tool_call_signature:
                consecutive_replan_count += 1
            else:
                consecutive_replan_count = 0
            last_tool_call_signature = current_call_signature

            if consecutive_replan_count >= 2:
                last_result_summary = ""
                if tool_history:
                    last_item = tool_history[-1]
                    if isinstance(last_item, dict):
                        obs = last_item.get("observation")
                        if obs and hasattr(obs, "summary"):
                            last_result_summary = str(obs.summary)[:500]
                        elif last_item.get("result"):
                            last_result_summary = str(last_item["result"])[:500]
                response_message = (
                    f"工具已连续重复调用 {consecutive_replan_count + 1} 次，自动终止循环。\n\n"
                    f"最后一次工具结果摘要：\n{last_result_summary}"
                )
                self._append_assistant_part(
                    run,
                    AssistantMessagePartV2(type="text", text=response_message, status="completed"),
                )
                run.trace.append(
                    TraceEventV2(
                        node="runtime",
                        event="loop_terminated_duplicate_calls",
                        detail=f"Terminated after {consecutive_replan_count + 1} consecutive identical tool calls.",
                    )
                )
                self._finalize_run(
                    run=run,
                    session_id=session_id,
                    persist_messages=persist_messages,
                    message=response_message,
                    status="completed",
                    replan_count=consecutive_replan_count,
                    delegation_count=0,
                    trace_event="run_finalized",
                    trace_detail="Run finalized after detecting duplicate tool calls.",
                )
                emit_event(
                    event="assistant.delta",
                    detail="Auto-terminated duplicate tool call loop.",
                    output_message=response_message,
                    run_status="completed",
                )
                emit_event(
                    event="run.completed",
                    detail="Run completed after detecting duplicate tool calls.",
                    output_message=response_message,
                    run_status="completed",
                    include_run=True,
                )
                return

        failure_message = (
            f"Agent reached max steps ({max_steps}) without producing a final reply. "
            f"Increase AGENT_LLM_AGENT_MAX_STEPS or check if the task is too complex."
        )
        self._append_assistant_part(
            run,
            AssistantMessagePartV2(type="error", text=failure_message, status="failed"),
        )
        run.observation = ObservationV2(
            source="agent.runtime",
            status="error",
            summary=failure_message,
            payload={"max_steps": max_steps},
        )
        self._finalize_run(
            run=run,
            session_id=session_id,
            persist_messages=persist_messages,
            message=failure_message,
            status="failed",
            replan_count=0,
            delegation_count=0,
            trace_event="run_failed",
            trace_detail="Run failed because the max agent step budget was exceeded.",
        )
        emit_event(
            event="run.failed",
            detail="Run failed because the max agent step budget was exceeded.",
            observation=run.observation,
            output_message=failure_message,
            run_status="failed",
            include_run=True,
        )

    def _llm_decide_use_direct_reply(
        self,
        *,
        user_message: str,
        request_context: RequestContextV2,
        recent_messages: list[SessionMessage],
    ) -> bool:
        if self._llm_provider is None or request_context.conversation_mode != "chat":
            return False
        message = user_message.strip()
        if not message:
            return False
        if request_context.image_path or request_context.attachments:
            return False
        if request_context.task_type is not None:
            return False
        try:
            recent_snippet = ""
            if recent_messages:
                last_few = recent_messages[-3:]
                recent_snippet = "\n".join(f"{m.role}: {m.content[:80]}" for m in last_few)
            routing_prompt = (
                "判断以下用户消息是否需要调用外部工具（如数据分析、文件处理、知识检索、报告生成等）才能回答。\n"
                "如果只需一般对话、闲聊、解释概念、回答常识问题，不需要任何工具 → 回复 DIRECT\n"
                "如果需要调用工具才能完成 → 回复 AGENT\n"
                "只回复 DIRECT 或 AGENT，不要其他内容。"
            )
            user_prompt = f"最近对话:\n{recent_snippet}\n当前用户消息: {message}"
            raw = self._llm_provider.generate_text(
                system_prompt=routing_prompt,
                user_prompt=user_prompt,
                max_tokens=8,
            )
            decision = raw.strip().upper()
            return decision.startswith("DIRECT")
        except Exception:
            return False

    def _should_use_direct_chat_reply(
        self,
        *,
        user_message: str,
        request_context: RequestContextV2,
    ) -> bool:
        if self._llm_provider is None or request_context.conversation_mode != "chat":
            return False
        message = user_message.strip().lower()
        if not message:
            return False
        if request_context.image_path or request_context.attachments:
            return False
        tool_intent_markers = (
            ".tif",
            ".tiff",
            ".png",
            "/data/",
            "分析",
            "检测",
            "报告",
            "可视化",
            "置信度",
            "训练",
            "workflow",
            "inference",
            "反演",
            "斑秃",
            "baldness",
            "alopecia",
        )
        return not any(marker in message for marker in tool_intent_markers)

    def _build_invalid_image_path_clarification(
        self,
        *,
        user_message: str,
        request_context: RequestContextV2,
    ) -> str | None:
        image_path = (request_context.image_path or "").strip()
        if not image_path:
            return None
        if not self._looks_like_analysis_request(user_message=user_message, request_context=request_context):
            return None
        expanded_path = Path(image_path).expanduser()
        if expanded_path.exists() and expanded_path.is_file():
            return None
        return (
            "要做真实分析，我需要当前机器上真实存在的本地影像路径。"
            f"你给的 `{image_path}` 不存在或不是文件。"
            "请通过下方 path chip 添加实际的 `.tif`/`.tiff` 文件，或直接发送真实绝对路径后再试。"
        )

    @staticmethod
    def _looks_like_analysis_request(
        *,
        user_message: str,
        request_context: RequestContextV2,
    ) -> bool:
        if request_context.conversation_mode == "task" or request_context.task_type is not None:
            return True
        lowered = user_message.strip().lower()
        if not lowered:
            return False
        return any(
            marker in lowered
            for marker in (
                "分析",
                "检测",
                "报告",
                "可视化",
                "置信度",
                "长势",
                "估产",
                "workflow",
                "report",
                "confidence",
                "visualization",
                "visualize",
                ".tif",
                ".tiff",
            )
        )

    def _generate_direct_chat_reply(
        self,
        *,
        user_message: str,
        request_context: RequestContextV2,
        recent_messages: list[SessionMessage],
        last_task_digest: dict[str, object] | None,
        session_id: str = "",
    ) -> str:
        if self._llm_provider is None:
            raise AgentLLMError("direct_chat_reply_requires_llm_provider")

        from v2.runtime.context import build_smart_context

        max_context = self._llm_config.context_window_tokens - self._llm_config.context_reserve_output_tokens
        context_messages, summary = _run_async_or_sync(
            build_smart_context(
                recent_messages,
                user_message,
                self._llm_provider,
                session_id=session_id,
                max_messages=self._llm_config.context_history_messages,
                max_chars_per_message=self._llm_config.context_message_max_chars,
                max_context_tokens=max_context,
            )
        )

        history_lines = [
            f"{item.role}: {item.content}"
            for item in context_messages
        ]

        if summary:
            history_lines.insert(0, summary)

        digest_summary = ""
        if isinstance(last_task_digest, dict) and last_task_digest:
            digest_summary = (
                "\n最近一次任务摘要: "
                + "; ".join(
                    f"{key}={str(value)[:120]}"
                    for key, value in last_task_digest.items()
                    if value is not None
                )
            )
        user_prompt = (
            f"最近对话:\n{chr(10).join(history_lines) if history_lines else '(empty)'}"
            f"{digest_summary}\n"
            f"当前用户消息: {user_message}\n"
            "请像一个自然的通用智能体一样直接回答。"
            "如果这是普通聊天、身份询问、比较、解释或延续上下文的问题，就直接回答，不要谈内部 runtime、planner、JSON。"
            "如果用户其实是在要求真实分析但缺少关键输入，只用一句话简洁追问。"
        )
        budgets = [self._llm_config.chat_max_new_tokens]
        retry_budget = min(
            self._llm_config.max_new_tokens,
            max(self._llm_config.chat_max_new_tokens * 2, 384),
        )
        if retry_budget > budgets[0]:
            budgets.append(retry_budget)
        last_error: AgentLLMError | None = None
        for budget_index, budget in enumerate(budgets):
            try:
                response_message = self._llm_provider.generate_text(
                    system_prompt=(
                        "你是 KTP Chat-First Agent。"
                        "默认表现为自然的通用智能体，只有在用户明确进入遥感分析任务时才强调 KTP 能力。"
                        f"当前入口={request_context.entrypoint}。"
                    ),
                    user_prompt=user_prompt,
                    max_tokens=budget,
                ).strip()
                if not response_message:
                    raise AgentLLMError(
                        "Upstream LLM returned an empty assistant message.",
                        category="incomplete_generation",
                        request_kind="direct_reply",
                        max_tokens=budget,
                    )
                return response_message
            except AgentLLMError as exc:
                last_error = exc
                if exc.category == "incomplete_generation" and budget_index < len(budgets) - 1:
                    logger.info(
                        "v2_direct_reply_retrying_for_incomplete_generation | initial_budget=%s | retry_budget=%s",
                        budget,
                        budgets[budget_index + 1],
                    )
                    continue
                raise
        if last_error is None:
            raise RuntimeError("LLM provider retry exhausted but no error captured")
        raise last_error

    def _describe_llm_failure(self, error: AgentLLMError, *, phase: str) -> str:
        if error.category == "upstream_overloaded":
            if phase == "direct_reply":
                return f"Upstream LLM unavailable or overloaded during direct reply: {error}"
            return f"Upstream LLM unavailable or overloaded during structured planning: {error}"
        if error.category == "incomplete_generation":
            if phase == "direct_reply":
                return f"Upstream LLM returned an incomplete answer during direct reply: {error}"
            return f"Upstream LLM returned incomplete structured output during planning: {error}"
        if error.category == "schema_mismatch":
            return f"Upstream LLM returned a schema-mismatched planner step: {error}"
        if phase == "direct_reply":
            return f"LLM direct reply failed: {error}"
        return f"LLM planning failed: {error}"

    def _build_llm_error_payload(
        self,
        error: AgentLLMError,
        *,
        step_index: int,
    ) -> dict[str, object]:
        return {"step_index": step_index, **error.to_payload()}

    def _append_llm_error_trace(
        self,
        *,
        run: RunDetail,
        error: AgentLLMError,
        phase: str,
    ) -> None:
        event_name = {
            "upstream_overloaded": "llm_upstream_overloaded",
            "incomplete_generation": "llm_incomplete_generation",
            "schema_mismatch": "llm_schema_mismatch",
        }.get(error.category, "llm_request_failed")
        run.trace.append(
            TraceEventV2(
                node="llm",
                event=event_name,
                detail=f"{phase} failed with category={error.category}: {error}",
            )
        )

    def _consume_llm_call_metadata(self) -> dict[str, object]:
        if self._llm_provider is None:
            return {}
        metadata = getattr(self._llm_provider, "last_call_metadata", None)
        if not isinstance(metadata, dict):
            return {}
        consumed = dict(metadata)
        try:
            setattr(self._llm_provider, "last_call_metadata", {})
        except Exception:
            logger.debug("v2_runtime_consume_metadata_setattr_failed")
        return consumed

    def _execute_single_tool_call(
        self,
        *,
        run: RunDetail,
        request_context: RequestContextV2,
        tool_call,
        visible_tools,
        visible_agents,
        policy,
        emit_event: Callable[..., None],
    ) -> dict[str, object]:
        spec = self._tool_registry.get_definition(tool_call.tool_name).spec
        invocation = ToolInvocationView(
            call_id=tool_call.call_id or str(uuid4()),
            tool_name=tool_call.tool_name,
            display_name=spec.display_name,
            category=spec.category,
            safety_level=spec.safety_level,
            status="running",
            requires_confirmation=spec.user_confirmation_required,
            tool_input=tool_call.tool_input,
            output_summary="started",
            result_preview="started",
            is_user_visible=spec.surface_visibility in {"all", "web", "api"},
        )
        self._append_assistant_part(
            run,
            AssistantMessagePartV2(type="tool_call", tool_invocation=invocation),
        )
        emit_event(
            event="tool.started",
            detail=f"Starting tool {tool_call.tool_name}.",
            tool_invocation=invocation,
        )

        if spec.user_confirmation_required:
            blocked_invocation = invocation.model_copy(
                update={
                    "status": "approval_required",
                    "output_summary": "approval_required",
                    "result_preview": "approval_required",
                }
            )
            run.tool_invocations.append(blocked_invocation)
            run.trace.append(
                TraceEventV2(
                    node="policy_guard",
                    event="approval_required",
                    detail=f"Tool {tool_call.tool_name} requires approval before execution.",
                )
            )
            observation = ObservationV2(
                source=tool_call.tool_name,
                status="error",
                summary="approval_required",
                payload={"tool_name": tool_call.tool_name, "tool_input": tool_call.tool_input},
            )
            self._append_assistant_part(
                run,
                AssistantMessagePartV2(
                    type="tool_result",
                    tool_invocation=blocked_invocation,
                    text="approval_required",
                    status="approval_required",
                ),
            )
            emit_event(
                event="tool.blocked",
                detail=f"Tool {tool_call.tool_name} requires approval before execution.",
                observation=observation,
                tool_invocation=blocked_invocation,
            )
            return {
                "blocked": True,
                "observation": observation,
                "final_message": f"Tool {tool_call.tool_name} requires approval before execution.",
                "history_item": {
                    "tool_name": tool_call.tool_name,
                    "status": "approval_required",
                    "summary": "approval_required",
                },
            }

        action = ExecutorActionV2(
            action_type="run_pack_flow" if spec.is_macro and tool_call.tool_name == "ktp.analysis_pipeline" else "invoke_tool",
            tool_name=tool_call.tool_name,
            tool_input=tool_call.tool_input,
            pack_name=spec.pack_name,
            flow_name="analysis_pipeline" if tool_call.tool_name == "ktp.analysis_pipeline" else None,
        )
        macro_invocation_index: int | None = None
        try:
            self._guard.validate_action(
                action=ExecutorActionV2(
                    action_type="invoke_tool",
                    tool_name=tool_call.tool_name,
                    tool_input=tool_call.tool_input,
                ),
                policy=policy,
                visible_tools=visible_tools,
                visible_agents=visible_agents,
                replan_count=0,
                delegation_count=0,
            )
            if action.action_type == "run_pack_flow":
                macro_invocation_index = len(run.tool_invocations)
                run.tool_invocations.append(invocation)
                observation, artifacts, final_message = self._execute_ktp_pack_flow(
                    run=run,
                    action=action,
                    policy=policy,
                    visible_tools=self._tool_registry.list_tools(),
                    visible_agents=visible_agents,
                    replan_count=0,
                    delegation_count=0,
                    event_sink=emit_event,
                )
            else:
                observation, artifacts = self._tool_registry.invoke(
                    tool_name=tool_call.tool_name,
                    tool_input=tool_call.tool_input,
                )
                final_message = observation.summary
        except PolicyGuardError as exc:
            observation = ObservationV2(
                source=tool_call.tool_name,
                status="error",
                summary=str(exc),
                payload={"tool_name": tool_call.tool_name, "tool_input": tool_call.tool_input},
            )
            artifacts = []
            final_message = str(exc)
        except Exception as exc:
            observation = ObservationV2(
                source=tool_call.tool_name,
                status="error",
                summary=str(exc),
                payload={"tool_name": tool_call.tool_name, "tool_input": tool_call.tool_input},
            )
            artifacts = []
            final_message = str(exc)

        completed_invocation = invocation.model_copy(
            update={
                "status": "success" if observation.status == "success" else "error",
                "output_summary": observation.summary,
                "result_preview": observation.summary,
            }
        )
        if macro_invocation_index is not None:
            run.tool_invocations[macro_invocation_index] = completed_invocation
        else:
            run.tool_invocations.append(completed_invocation)
        self._append_assistant_part(
            run,
            AssistantMessagePartV2(
                type="tool_result",
                tool_invocation=completed_invocation,
                text=observation.summary,
                status=observation.status,
            ),
        )
        run.trace.append(
            TraceEventV2(
                node="tool_dispatch",
                event="tool_finished" if observation.status == "success" else "tool_failed",
                detail=f"Tool {tool_call.tool_name} returned status={observation.status}.",
            )
        )
        emit_event(
            event="tool.completed",
            detail=f"Tool {tool_call.tool_name} returned status={observation.status}.",
            observation=observation,
            tool_invocation=completed_invocation,
        )

        for artifact in artifacts:
            if artifact not in run.artifacts:
                run.artifacts.append(artifact)
            self._append_assistant_part(
                run,
                AssistantMessagePartV2(type="artifact", artifact=artifact),
            )
            emit_event(
                event="artifact.available",
                detail=f"Artifact {artifact.title} is now available.",
                artifact=artifact,
            )

        return {
            "blocked": False,
            "observation": observation,
            "final_message": final_message,
            "history_item": {
                "tool_name": tool_call.tool_name,
                "status": observation.status,
                "summary": observation.summary,
                "artifacts": [artifact.title for artifact in artifacts],
            },
        }

    def _resolve_request_context(
        self,
        *,
        request_context: RequestContextV2 | None,
        user_message: str,
    ) -> RequestContextV2:
        context = request_context.model_copy(deep=True) if request_context is not None else RequestContextV2()
        if context.entrypoint == "detect":
            context.conversation_mode = "task"
        if context.task_type is None:
            context.task_type = detect_task_type_from_text(
                user_message,
                default="crop_health_detection" if context.conversation_mode == "task" else None,
            )
        context.region = context.region or detect_region_from_text(user_message)
        context.crop_type = context.crop_type or detect_crop_type_from_text(user_message)
        if context.task_type == "baldness_detection":
            context.region = context.region or "scalp"
            context.crop_type = context.crop_type or "hair"
        context.image_path = context.image_path or extract_image_path_from_text(user_message)
        if context.image_path and not context.attachments:
            context.attachments = [
                AttachmentV2(
                    path=context.image_path,
                    name=context.image_path.split("/")[-1],
                )
            ]
        return context

    def _resolve_visible_tools(self, *, request_context: RequestContextV2) -> list:
        allowed_categories = None
        if request_context.conversation_mode == "task":
            allowed_categories = {"analysis", "knowledge", "report", "visualization", "training"}
        visible_tools = []
        for tool in self._tool_registry.list_tools():
            if not tool.enabled_by_default and tool.surface_visibility not in {"debug", "internal"}:
                continue
            if request_context.entrypoint in {"chat", "v2_ui", "api", "detect"}:
                if tool.surface_visibility not in {"all", "web", "api"}:
                    continue
            if allowed_categories is not None and tool.category not in allowed_categories:
                continue
            if tool.name.startswith("ktp.") and tool.name in {
                "ktp.lookup_model_registry",
                "ktp.run_inference_workflow",
                "ktp.retrieve_knowledge",
                "ktp.build_report",
                "ktp.evaluate_confidence",
                "ktp.build_visualization",
            }:
                continue
            visible_tools.append(tool)
        return visible_tools

    @staticmethod
    def _build_last_task_digest(previous_run: RunDetail | None) -> dict[str, object] | None:
        if previous_run is None or not previous_run.tool_invocations:
            return None
        return {
            "status": previous_run.status,
            "answer": previous_run.output_message,
            "artifacts": [artifact.title for artifact in previous_run.artifacts],
            "tool_chain": [tool.tool_name for tool in previous_run.tool_invocations],
        }

    @staticmethod
    def _build_current_task_digest(run: RunDetail) -> dict[str, object] | None:
        if not run.tool_invocations:
            return None
        return {
            "status": run.status,
            "answer": run.output_message,
            "artifacts": [artifact.title for artifact in run.artifacts],
            "tool_chain": [tool.tool_name for tool in run.tool_invocations],
        }

    @staticmethod
    def _append_assistant_part(run: RunDetail, part: AssistantMessagePartV2) -> None:
        if run.assistant_message is None:
            run.assistant_message = AssistantMessageV2(parts=[])
        run.assistant_message.parts.append(part)

    @staticmethod
    def _message_requests_knowledge(message: str) -> bool:
        normalized = message.lower()
        return any(keyword in normalized for keyword in ("资料", "来源", "source", "reference", "ndvi", "evi", "explain"))

    @staticmethod
    def _message_requests_visualization(message: str) -> bool:
        normalized = message.lower()
        return any(keyword in normalized for keyword in ("可视化", "dashboard", "visualization", "图", "map"))

    def _execute_ktp_pack_flow(
        self,
        *,
        run: RunDetail,
        action: ExecutorActionV2,
        policy,
        visible_tools,
        visible_agents,
        replan_count: int,
        delegation_count: int,
        event_sink: Callable[..., None] | None = None,
    ) -> tuple[ObservationV2, list, str]:
        bundle = self._tool_registry.ktp_service_bundle
        if bundle is None:
            observation = ObservationV2(
                source="ktp.pack_flow",
                status="error",
                summary="KTP service bundle is not configured in the active tool registry.",
                payload={"pack_name": action.pack_name, "flow_name": action.flow_name},
            )
            return observation, [], observation.summary

        flow_input = dict(action.tool_input)
        query = str(flow_input.get("query") or run.input_message)
        extra_params = dict(flow_input.get("extra_params") or {})
        include_knowledge = bool(
            flow_input.pop("include_knowledge", False)
            or extra_params.get("include_knowledge")
            or self._message_requests_knowledge(query)
        )
        include_visualization = bool(
            flow_input.pop("include_visualization", False)
            or extra_params.get("include_visualization")
            or self._message_requests_visualization(query)
        )
        top_k = int(flow_input.pop("top_k", 3) or 3)
        extra_params["include_knowledge"] = include_knowledge
        extra_params["include_visualization"] = include_visualization

        _lai_keywords = {"lai", "leaf area index", "叶面积指数", "叶面积"}
        _baldness_keywords = {"斑秃", "秃斑", "脱发", "baldness", "alopecia"}
        _query_lower = query.lower()
        _is_lai_query = any(kw in _query_lower for kw in _lai_keywords)
        _is_baldness_query = any(kw in _query_lower for kw in _baldness_keywords)
        if _is_lai_query:
            extra_params["task_type"] = "lai_inversion"
        elif _is_baldness_query:
            extra_params["task_type"] = "baldness_detection"
            if not flow_input.get("region"):
                flow_input["region"] = "scalp"
            if not flow_input.get("crop_type"):
                flow_input["crop_type"] = "hair"

        context = bundle.create_context(
            query=query,
            region=str(flow_input.get("region") or extra_params.pop("region", "") or KTP_DEFAULT_REGION),
            crop_type=str(flow_input.get("crop_type") or extra_params.pop("crop_type", "") or KTP_DEFAULT_CROP_TYPE),
            task_type=str(flow_input.get("task_type") or extra_params.pop("task_type", "") or KTP_DEFAULT_TASK_TYPE),
            request_id=str(flow_input.get("request_id") or run.run_id),
            use_mock_backend=bool(flow_input.get("use_mock_backend", False)),
            image_path=str(flow_input.get("image_path")) if flow_input.get("image_path") else None,
            top_k=top_k,
            extra_params=extra_params,
        )

        artifacts = []
        step_names = []
        if context.task_type != "lai_inversion":
            step_names.append("ktp.lookup_model_registry")
        step_names.append("ktp.run_inference_workflow")
        if include_knowledge:
            step_names.append("ktp.retrieve_knowledge")
        step_names.extend(["ktp.build_report", "ktp.evaluate_confidence"])
        if include_visualization:
            step_names.append("ktp.build_visualization")

        if event_sink is not None and context.image_path:
            try:
                img_size = Path(context.image_path).stat().st_size
                size_mb = img_size / (1024 * 1024)
                if size_mb > 100:
                    event_sink(
                        event="assistant.status",
                        detail=f"正在处理大文件（{size_mb:.0f} MB），预计需要较长时间，请耐心等待...",
                    )
            except OSError:
                pass

        for step_name in step_names:
            step_action = ExecutorActionV2(
                action_type="invoke_tool",
                tool_name=step_name,
                tool_input=self._build_pack_step_input(context=context, step_name=step_name),
            )
            if event_sink is not None:
                event_sink(
                    event="tool.started",
                    detail=f"开始执行 KTP 流程步骤 {step_name}。",
                    tool_invocation=ToolInvocationView(
                        call_id=f"{run.run_id}:{step_name}",
                        tool_name=step_name,
                        display_name=self._tool_registry.get_definition(step_name).spec.display_name,
                        category=self._tool_registry.get_definition(step_name).spec.category,
                        safety_level=self._tool_registry.get_definition(step_name).spec.safety_level,
                        status="running",
                        tool_input=step_action.tool_input,
                        result_preview="started",
                        output_summary="started",
                        is_user_visible=False,
                    ),
                )
            try:
                self._guard.validate_action(
                    action=step_action,
                    policy=policy,
                    visible_tools=visible_tools,
                    visible_agents=visible_agents,
                    replan_count=replan_count,
                    delegation_count=delegation_count,
                )
                step_observation, step_artifacts = self._run_ktp_step(step_name=step_name, context=context)
                artifacts.extend(step_artifacts)
                run.tool_invocations.append(
                    ToolInvocationView(
                        call_id=f"{run.run_id}:{step_name}",
                        tool_name=step_name,
                        display_name=self._tool_registry.get_definition(step_name).spec.display_name,
                        category=self._tool_registry.get_definition(step_name).spec.category,
                        safety_level=self._tool_registry.get_definition(step_name).spec.safety_level,
                        status="success",
                        tool_input=step_action.tool_input,
                        result_preview=step_observation.summary,
                        output_summary=step_observation.summary,
                        is_user_visible=False,
                    )
                )
                run.trace.append(
                    TraceEventV2(
                        node="tool_dispatch",
                        event="tool_finished",
                        detail=f"KTP 流程步骤 {step_name} 执行成功。",
                    )
                )
                if event_sink is not None:
                    event_sink(
                        event="tool.completed",
                        detail=f"KTP 流程步骤 {step_name} 执行成功。",
                        observation=step_observation,
                        tool_invocation=run.tool_invocations[-1],
                    )
                    for artifact in step_artifacts:
                        event_sink(
                            event="artifact.available",
                            detail=f"已输出 {step_name} 的产物。",
                            artifact=artifact,
                        )
            except Exception as exc:
                error_payload = _context_payload(context)
                error_payload["failed_step"] = step_name
                error_payload["error"] = str(exc)
                run.tool_invocations.append(
                    ToolInvocationView(
                        call_id=f"{run.run_id}:{step_name}",
                        tool_name=step_name,
                        display_name=self._tool_registry.get_definition(step_name).spec.display_name,
                        category=self._tool_registry.get_definition(step_name).spec.category,
                        safety_level=self._tool_registry.get_definition(step_name).spec.safety_level,
                        status="error",
                        tool_input=step_action.tool_input,
                        result_preview=str(exc),
                        output_summary=str(exc),
                        is_user_visible=False,
                    )
                )
                run.trace.append(
                    TraceEventV2(
                        node="tool_dispatch",
                        event="tool_failed",
                        detail=f"KTP 流程步骤 {step_name} 失败: {exc}",
                    )
                )
                observation = ObservationV2(
                    source="ktp.pack_flow",
                    status="error",
                    summary=f"KTP 单智能体流程在步骤 {step_name} 失败: {exc}",
                    payload=error_payload,
                )
                if event_sink is not None:
                    event_sink(
                        event="tool.completed",
                        detail=f"KTP 流程步骤 {step_name} 失败: {exc}",
                        observation=observation,
                        tool_invocation=run.tool_invocations[-1],
                    )
                return observation, artifacts, observation.summary

        final_observation = ObservationV2(
            source="ktp.pack_flow",
            status="success",
            summary="KTP 单智能体流程执行完成。",
            payload=_context_payload(context),
        )
        return (
            final_observation,
            artifacts,
            self._build_ktp_pack_flow_success_message(
                context=context,
                include_knowledge=include_knowledge,
                include_visualization=include_visualization,
            ),
        )

    @staticmethod
    def _build_pack_step_input(*, context: KtpExecutionContext, step_name: str) -> dict[str, object]:
        payload = {
            "query": context.query,
            "region": context.region,
            "crop_type": context.crop_type,
            "task_type": context.task_type,
            "request_id": context.request_id,
            "use_mock_backend": context.use_mock_backend,
            "image_path": context.image_path,
            "top_k": context.top_k,
            "extra_params": dict(context.extra_params),
        }
        if step_name == "ktp.retrieve_knowledge":
            payload["top_k"] = context.top_k
        return payload

    def _run_ktp_step(
        self,
        *,
        step_name: str,
        context: KtpExecutionContext,
    ) -> tuple[ObservationV2, list]:
        if step_name == "ktp.lookup_model_registry":
            bundle = self._tool_registry.ktp_service_bundle
            if bundle is None:
                raise KtpServiceError("KTP service bundle not available for model registry lookup")
            result = bundle.ensure_model_lookup(context)
            return (
                ObservationV2(
                    source=step_name,
                    status="success",
                    summary=(
                        f"KTP 模型注册查询完成，model_exists={result.model_exists}，"
                        f"区域={context.region}/{context.crop_type}/{context.task_type}。"
                    ),
                    payload=_context_payload(context),
                ),
                [
                    _artifact_from_model_lookup(
                        result=result,
                        backend=context.model_lookup_backend or "unknown",
                        context=context,
                    )
                ],
            )

        bundle = self._tool_registry.ktp_service_bundle
        if bundle is None:
            raise KtpServiceError("KTP service bundle not available for pack flow execution")

        if step_name == "ktp.run_inference_workflow":
            result = bundle.ensure_inference(context)
            return (
                ObservationV2(
                    source=step_name,
                    status="success",
                    summary=(
                        f"KTP 推理工作流完成，confidence={result.confidence:.2f}，"
                        f"{'LAI' if context.task_type == 'lai_inversion' else 'affected_area'}={result.affected_area:.2f}。"
                    ),
                    payload=_context_payload(context),
                ),
                [
                    _artifact_from_inference(
                        result=result,
                        backend=context.inference_backend or "unknown",
                        task_type=context.task_type,
                    )
                ],
            )

        if step_name == "ktp.retrieve_knowledge":
            result = bundle.ensure_knowledge(context)
            return (
                ObservationV2(
                    source=step_name,
                    status="success",
                    summary=(
                        f"KTP 知识检索完成，获取 {len(result.results)} 个片段，"
                        f"{len(result.sources)} 个来源。"
                    ),
                    payload=_context_payload(context),
                ),
                [],
            )

        if step_name == "ktp.build_report":
            result = bundle.ensure_report(context)
            return (
                ObservationV2(
                    source=step_name,
                    status="success",
                    summary=(
                        f"KTP 报告生成完成，共 {len(result.sections)} 个章节，"
                        f"backend={context.report_backend or 'unknown'}。"
                    ),
                    payload=_context_payload(context),
                ),
                [
                    _artifact_from_report(
                        result=result,
                        backend=context.report_backend or "unknown",
                    )
                ],
            )

        if step_name == "ktp.evaluate_confidence":
            result = bundle.ensure_confidence(context)
            return (
                ObservationV2(
                    source=step_name,
                    status="success",
                    summary=(
                        f"KTP 置信度评估完成，final_confidence={result.final_confidence:.2f}，"
                        f"label={result.final_label or 'unknown'}。"
                    ),
                    payload=_context_payload(context),
                ),
                [
                    _artifact_from_confidence(
                        result=result,
                        backend=context.confidence_backend or "unknown",
                    )
                ],
            )

        if step_name == "ktp.build_visualization":
            result = bundle.ensure_visualization(context)
            return (
                ObservationV2(
                    source=step_name,
                    status="success",
                    summary=(
                        f"KTP 可视化生成完成，共 {len(result.sections)} 个仪表盘章节，"
                        f"backend={context.visualization_backend or 'unknown'}。"
                    ),
                    payload=_context_payload(context),
                ),
                [
                    _artifact_from_visualization(
                        result=result,
                        backend=context.visualization_backend or "unknown",
                    )
                ],
            )

        raise KtpServiceError(f"Unsupported KTP pack flow step: {step_name}")

    def _build_run_state(self, run: RunDetail) -> RunStateV2:
        return RunStateV2(
            run=run,
            policy=self._policy_registry.get_default_policy(),
            visible_tools=self._tool_registry.list_tools(),
            visible_agents=self._agent_registry.list_profiles(),
        )

    @staticmethod
    def _compare_runs(*, original_run: RunDetail, replayed_run: RunDetail) -> ReplayComparisonV2:
        checks = {
            "status_match": original_run.status == replayed_run.status,
            "planner_action_match": (
                (original_run.planner_decision.action if original_run.planner_decision else None)
                == (replayed_run.planner_decision.action if replayed_run.planner_decision else None)
            ),
            "planner_reasoning_match": (
                (original_run.planner_decision.reasoning if original_run.planner_decision else None)
                == (replayed_run.planner_decision.reasoning if replayed_run.planner_decision else None)
            ),
            "executor_action_match": (
                BoundedRuntimeEngine._model_dump(original_run.executor_action)
                == BoundedRuntimeEngine._model_dump(replayed_run.executor_action)
            ),
            "output_message_match": original_run.output_message == replayed_run.output_message,
            "observation_source_match": (
                (original_run.observation.source if original_run.observation else None)
                == (replayed_run.observation.source if replayed_run.observation else None)
            ),
            "observation_status_match": (
                (original_run.observation.status if original_run.observation else None)
                == (replayed_run.observation.status if replayed_run.observation else None)
            ),
            "observation_summary_match": (
                (original_run.observation.summary if original_run.observation else None)
                == (replayed_run.observation.summary if replayed_run.observation else None)
            ),
            "observation_payload_match": (
                (original_run.observation.payload if original_run.observation else None)
                == (replayed_run.observation.payload if replayed_run.observation else None)
            ),
            "delegation_status_match": (
                (original_run.delegation.status if original_run.delegation else None)
                == (replayed_run.delegation.status if replayed_run.delegation else None)
            ),
            "delegation_target_match": (
                (original_run.delegation.target_agent if original_run.delegation else None)
                == (replayed_run.delegation.target_agent if replayed_run.delegation else None)
            ),
            "tool_invocation_count_match": len(original_run.tool_invocations) == len(replayed_run.tool_invocations),
            "tool_invocation_sequence_match": (
                [tool.model_dump(mode="json") for tool in original_run.tool_invocations]
                == [tool.model_dump(mode="json") for tool in replayed_run.tool_invocations]
            ),
            "artifact_count_match": len(original_run.artifacts) == len(replayed_run.artifacts),
            "artifact_sequence_match": (
                [artifact.model_dump(mode="json") for artifact in original_run.artifacts]
                == [artifact.model_dump(mode="json") for artifact in replayed_run.artifacts]
            ),
            "replan_count_match": original_run.replan_count == replayed_run.replan_count,
            "delegation_count_match": original_run.delegation_count == replayed_run.delegation_count,
            "trace_event_count_match": len(original_run.trace) == len(replayed_run.trace),
            "trace_event_sequence_match": (
                [event.model_dump(mode="json") for event in original_run.trace]
                == [event.model_dump(mode="json") for event in replayed_run.trace]
            ),
        }
        mismatch_fields = [field_name for field_name, matched in checks.items() if not matched]
        return ReplayComparisonV2(
            overall_match=not mismatch_fields,
            mismatch_fields=mismatch_fields,
            **checks,
        )

    @staticmethod
    def _model_dump(model: object | None) -> dict[str, object] | None:
        if model is None:
            return None
        return model.model_dump(mode="json")

    @staticmethod
    def _build_success_message(*, observation: ObservationV2) -> str:
        if observation.source == "demo.pack_answer":
            return "Demo pack 工具执行成功，runtime 已完成一次受限工具调用闭环。"
        if observation.source == "ktp.retrieve_knowledge":
            return "KTP 知识检索已完成，智能体返回了可追溯资料来源。"
        if observation.source == "ktp.trigger_training":
            return "KTP 训练任务已显式触发。"
        return observation.summary

    @staticmethod
    def _build_ktp_pack_flow_success_message(
        *,
        context: KtpExecutionContext,
        include_knowledge: bool,
        include_visualization: bool,
    ) -> str:
        model_name = context.inference_result.model_name if context.inference_result is not None else "unknown"
        confidence = (
            f"{context.confidence_result.final_confidence:.2f}"
            if context.confidence_result is not None
            else "n/a"
        )
        knowledge_phrase = "并补充知识依据" if include_knowledge and context.rag_result is not None else ""
        visualization_phrase = "，同时生成了可视化结果" if include_visualization else ""
        return (
            f"KTP 智能体已完成模型检查、推理、报告和置信度评估{knowledge_phrase}{visualization_phrase}。"
            f"当前模型为 {model_name}，最终置信度 {confidence}。"
        )

    @staticmethod
    def _handle_delegation(*, target_agent: str) -> str:
        return (
            f"V2 runtime 已完成一次受限 delegation，目标 agent 为 {target_agent}。"
            "当前仍保持可审计的 bounded delegation 行为。"
        )

    def _finalize_run(
        self,
        *,
        run: RunDetail,
        session_id: str,
        persist_messages: bool,
        message: str,
        status: str,
        replan_count: int,
        delegation_count: int,
        trace_event: str,
        trace_detail: str,
    ) -> None:
        assistant_entry = SessionMessage(role="assistant", content=message)
        if persist_messages:
            self._store.append_message(session_id, assistant_entry)
        run.output_message = message
        run.status = status
        run.replan_count = replan_count
        run.delegation_count = delegation_count
        run.trace.append(TraceEventV2(node="runtime", event=trace_event, detail=trace_detail))
