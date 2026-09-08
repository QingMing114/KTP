from __future__ import annotations

import logging
import asyncio
import json
from pathlib import Path
from queue import SimpleQueue
from threading import Event, Thread
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
from v2.agents.registry import AgentProfileRegistry
from v2.packs.registry import DomainPackRegistry
from v2.policies.guard import PolicyGuard, PolicyGuardError
from v2.policies.registry import PolicyRegistryV2
from v2.runtime.events import RunEventEmitter
from v2.runtime.cancellation import RuntimeCancellationError, raise_if_cancelled
from v2.runtime.executor import (
    ToolExecutor,
    append_assistant_part,
    build_ktp_pack_flow_success_message,
    build_pack_step_input,
)
from v2.runtime.memory_manager import MemoryManager
from v2.runtime.observer import RunObserver
from v2.runtime.planner import ChatFirstPlanner
from v2.runtime.store import RuntimeStore
from schemas.runtime import (
    AgentStepV2,
    AssistantMessagePartV2,
    AssistantMessageV2,
    AttachmentV2,
    DelegationResult,
    ExecutorActionV2,
    ObservationV2,
    ReplayComparisonV2,
    ReplayResponseV2,
    RequestContextV2,
    RunEventV2,
    RunDetail,
    RunStateV2,
    RuntimeRunStatus,
    SessionMessage,
    TraceEventV2,
)
from v2.tools.registry import ToolRegistryV2

logger = logging.getLogger(__name__)


def _run_async_or_sync(coro, timeout: float = 60):
    try:
        asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result(timeout=timeout)
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
        memory_dir: str | None = None,
        memory_top_k: int = 5,
        memory_max_chars: int = 2_000,
        memory_auto_write_enabled: bool = False,
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
        self._executor = ToolExecutor(
            tool_registry=tool_registry,
            policy_guard=self._guard,
            pack_registry=pack_registry,
        )
        self._memory_manager = MemoryManager(memory_dir=memory_dir) if memory_dir else None
        self._memory_top_k = memory_top_k
        self._memory_max_chars = memory_max_chars
        self._memory_auto_write_enabled = memory_auto_write_enabled

    def run(
        self,
        *,
        session_id: str,
        user_message: str,
        user_id: str | None,
        request_context: RequestContextV2 | None = None,
        cancellation_event: Event | None = None,
    ) -> RunDetail:
        run: RunDetail | None = None
        for event in self.stream(
            session_id=session_id,
            user_message=user_message,
            user_id=user_id,
            request_context=request_context,
            cancellation_event=cancellation_event,
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
        cancellation_event: Event | None = None,
    ) -> Iterator[RunEventV2]:
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
                    user_id=user_id,
                    request_context=request_context,
                    persist_messages=True,
                    persist_run=True,
                    replay_of_run_id=None,
                    event_sink=event_queue.put,
                    cancellation_event=cancellation_event,
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
            user_id="replay",
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
        user_id: str | None,
        request_context: RequestContextV2 | None,
        persist_messages: bool,
        persist_run: bool,
        replay_of_run_id: str | None,
        event_sink: Callable[[RunEventV2], None] | None,
        cancellation_event: Event | None = None,
    ) -> RunDetail:
        session = self._store.get_session(session_id)
        if session is None:
            raise KeyError(session_id)
        run = self._execute(
            session_id=session_id,
            user_message=user_message,
            user_id=user_id,
            request_context=request_context,
            persist_messages=persist_messages,
            persist_run=persist_run,
            replay_of_run_id=replay_of_run_id,
            event_sink=event_sink,
            cancellation_event=cancellation_event,
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
        cancellation_event: Event | None = None,
        user_id: str | None = None,
    ) -> RunDetail:
        session = self._store.get_session(session_id)
        if session is None:
            raise KeyError(session_id)

        raise_if_cancelled(cancellation_event)
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

        emitter = RunEventEmitter(
            sink=event_sink,
            run_id=run.run_id,
            session_id=session_id,
        )
        emitter.run = run
        emitter.emit(
            event="run.started",
            detail="Created bounded runtime run and loaded request visibility.",
            message=user_entry,
        )
        emitter.emit(
            event="assistant.status",
            detail=(
                f"Planning agent loop for entrypoint={resolved_context.entrypoint} with "
                f"{len(visible_tools)} visible tools."
            ),
        )

        max_steps = min(
            self._llm_config.agent_max_steps if hasattr(self._llm_config, 'agent_max_steps') else 20,
            30,
        )
        observer = RunObserver(max_steps=max_steps)
        tool_history: list[dict[str, object]] = []
        try:
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
                emitter=emitter,
                observer=observer,
                cancellation_event=cancellation_event,
                user_id=user_id,
            )
        except RuntimeCancellationError:
            cancellation_message = "Run cancelled by request."
            run.status = "cancelled"
            run.output_message = cancellation_message
            run.observation = ObservationV2(
                source="agent.runtime",
                status="error",
                summary=cancellation_message,
                payload={"reason": "cancelled"},
            )
            run.trace.append(
                TraceEventV2(
                    node="runtime",
                    event="run_cancelled",
                    detail="Stopped at a cooperative cancellation boundary.",
                )
            )
            emitter.emit(
                event="run.cancelled",
                detail=cancellation_message,
                observation=run.observation,
                output_message=cancellation_message,
                run_status="cancelled",
                include_run=True,
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
        emitter: RunEventEmitter,
        observer: RunObserver,
        cancellation_event: Event | None = None,
        user_id: str | None = None,
    ) -> None:
        raise_if_cancelled(cancellation_event)
        session = self._store.get_session(session_id)
        if session is None:
            raise KeyError(session_id)
        recent_messages = list(session.messages)

        # Phase B.1: compact conversation when the message history exceeds the window.
        context_summary = ""
        from v2.runtime.context import build_smart_context

        max_context = self._llm_config.context_window_tokens - self._llm_config.context_reserve_output_tokens
        context_messages, context_summary = _run_async_or_sync(
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
        raise_if_cancelled(cancellation_event)
        # build_smart_context always returns at least as-trimmed messages;
        # use the compacted window for planning when it differs meaningfully.
        if len(context_messages) != len(recent_messages) or context_summary:
            recent_messages = context_messages

        if context_summary:
            session.summary = context_summary
            self._store.save_session(session)

        # Phase B.2: retrieve project memory for the current planner request.
        # Keep it out of session history: a history-window trim must not discard
        # knowledge retrieved specifically for this turn.
        memory_context = ""
        if self._memory_manager is not None and self._memory_manager.is_loaded:
            memory_context = self._memory_manager.build_context_injection(
                query=user_message,
                top_k=self._memory_top_k,
                max_chars=self._memory_max_chars,
            )
            if memory_context:
                run.trace.append(
                    TraceEventV2(
                        node="memory",
                        event="memory_context_injected",
                        detail=(
                            f"Injected {len(memory_context)} characters of relevant Markdown knowledge "
                            f"for the current request."
                        ),
                    )
                )

        last_task_digest = self._build_last_task_digest(previous_latest_run)
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
            append_assistant_part(
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
            emitter.emit(
                event="assistant.delta",
                detail="Emitted the clarification response for the invalid local image path.",
                output_message=invalid_image_path_message,
                run_status="completed",
            )
            emitter.emit(
                event="run.completed",
                detail="Run completed with a clarification because the requested local image path does not exist.",
                observation=run.observation,
                output_message=invalid_image_path_message,
                run_status="completed",
                include_run=True,
            )
            return

        replan_count = 0
        delegation_count = 0

        for step_index in range(observer.max_steps):
            raise_if_cancelled(cancellation_event)
            try:
                agent_step = self._planner.plan(
                    message=user_message,
                    visible_tools=visible_tools,
                    request_context=request_context,
                    recent_messages=recent_messages,
                    tool_history=tool_history,
                    last_task_digest=last_task_digest,
                    memory_context=memory_context,
                )
            except AgentLLMError as exc:
                failure_message = self._describe_llm_failure(exc)
                append_assistant_part(
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
                    replan_count=replan_count,
                    delegation_count=delegation_count,
                    trace_event="run_failed",
                    trace_detail="Run failed because the chat-first planner could not obtain a valid LLM step.",
                )
                emitter.emit(
                    event="run.failed",
                    detail="Run failed because the chat-first planner could not obtain a valid LLM step.",
                    observation=run.observation,
                    output_message=run.output_message,
                    run_status="failed",
                    include_run=True,
                )
                return
            except Exception as exc:
                # Planner adapters are external boundaries; an unexpected
                # provider/stub error must still produce a terminal run event.
                prior_tool_failure = (
                    replan_count > 0
                    and run.observation is not None
                    and run.observation.status == "error"
                )
                failure_message = (
                    run.observation.summary
                    if prior_tool_failure and run.observation is not None
                    else f"Planner failed: {exc}"
                )
                if not prior_tool_failure:
                    run.observation = ObservationV2(
                        source="agent.planner",
                        status="error",
                        summary=failure_message,
                        payload={"step_index": step_index, "error_type": type(exc).__name__},
                    )
                append_assistant_part(
                    run,
                    AssistantMessagePartV2(type="error", text=failure_message, status="failed"),
                )
                run.trace.append(TraceEventV2(
                    node="planner",
                    event="planning_failed",
                    detail=f"{type(exc).__name__}: {exc}",
                ))
                self._finalize_run(
                    run=run,
                    session_id=session_id,
                    persist_messages=persist_messages,
                    message=failure_message,
                    status="failed",
                    replan_count=replan_count,
                    delegation_count=delegation_count,
                    trace_event="run_failed",
                    trace_detail="Run failed because replanning could not produce a valid next step.",
                )
                emitter.emit(
                    event="run.failed",
                    detail="Run failed because replanning could not produce a valid next step.",
                    observation=run.observation,
                    output_message=failure_message,
                    run_status="failed",
                    include_run=True,
                )
                return

            raise_if_cancelled(cancellation_event)
            run.agent_steps.append(agent_step)
            run.planner_decision = agent_step

            emitter.emit(
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
            emitter.emit(
                event="planner.delta",
                detail=f"Planner reasoning: {agent_step.reasoning[:200] if agent_step.reasoning else 'No reasoning provided'}",
                planner_decision=agent_step,
            )

            if agent_step.action in {"reply", "clarify"}:
                response_message = (agent_step.response_message or "").strip()
                if not response_message:
                    response_message = "The assistant returned an empty reply."
                part_type = "status" if agent_step.action == "clarify" else "text"
                append_assistant_part(
                    run,
                    AssistantMessagePartV2(type=part_type, text=response_message, status=agent_step.action),
                )
                self._finalize_run(
                    run=run,
                    session_id=session_id,
                    persist_messages=persist_messages,
                    message=response_message,
                    status="completed",
                    replan_count=replan_count,
                    delegation_count=delegation_count,
                    trace_event="run_finalized",
                    trace_detail=f"Run finalized after agent selected {agent_step.action}.",
                )
                emitter.emit(
                    event="assistant.delta",
                    detail="Emitted the final assistant response.",
                    output_message=response_message,
                    run_status="completed",
                )
                emitter.emit(
                    event="run.completed",
                    detail=f"Run finalized after agent selected {agent_step.action}.",
                    output_message=response_message,
                    run_status="completed",
                    include_run=True,
                )
                return

            if agent_step.action == "delegate":
                raise_if_cancelled(cancellation_event)
                target = agent_step.delegation_target or "executor_30b"
                goal = agent_step.delegation_goal or user_message

                try:
                    self._guard.validate_action(
                        action=ExecutorActionV2(action_type="delegate", target_agent=target),
                        policy=policy,
                        visible_tools=visible_tools,
                        visible_agents=visible_agents,
                        replan_count=replan_count,
                        delegation_count=delegation_count,
                    )
                except PolicyGuardError as exc:
                    failure_message = f"Delegation rejected by policy: {exc}"
                    run.observation = ObservationV2(
                        source="agent.policy",
                        status="error",
                        summary=failure_message,
                        payload={"delegation_target": target, "reason": str(exc)},
                    )
                    append_assistant_part(
                        run,
                        AssistantMessagePartV2(type="error", text=failure_message, status="failed"),
                    )
                    self._finalize_run(
                        run=run,
                        session_id=session_id,
                        persist_messages=persist_messages,
                        message=failure_message,
                        status="failed",
                        replan_count=replan_count,
                        delegation_count=delegation_count,
                        trace_event="run_failed",
                        trace_detail=failure_message,
                    )
                    emitter.emit(
                        event="run.failed",
                        detail=failure_message,
                        observation=run.observation,
                        output_message=failure_message,
                        run_status="failed",
                        include_run=True,
                    )
                    return

                emitter.emit(
                    event="run.progress",
                    detail=f"委派任务给 {target}：{goal[:100]}",
                    run_status="running",
                )

                # 创建受限工具集
                executor_registry = self._tool_registry.get_executor_subset()

                # 创建子执行器
                from v2.runtime.sub_executor import SubExecutor

                sub = SubExecutor(
                    tool_registry=executor_registry,
                    llm_provider=self._llm_provider,
                    policy=policy,
                    cancellation_event=cancellation_event,
                    user_id=user_id,
                )

                # 执行委派任务
                sub_result = sub.execute(
                    goal=goal,
                    request_context=request_context,
                    parent_emitter=emitter,
                    parent_run=run,
                )

                # 记录委派结果
                run.delegation = DelegationResult(
                    target_agent=target,
                    status="completed" if sub_result.success else "rejected",
                    summary=sub_result.summary,
                )
                delegation_count += 1

                if sub_result.success:
                    # merge artifacts into run so they get registered in ArtifactStore
                    run.artifacts.extend(sub_result.artifacts)
                    # merge tool_invocations for debug trace
                    for inv in sub_result.tool_invocations:
                        tool_inv = inv.get("tool_invocation") if isinstance(inv, dict) else None
                        if tool_inv is not None:
                            run.tool_invocations.append(tool_inv)
                    tool_history.append({
                        "role": "tool",
                        "content": f"[{target}] {sub_result.summary}",
                        "tool_call_id": f"delegation_{step_index}",
                    })
                    continue  # 让 planner 在下一轮汇总
                else:
                    failure_message = f"委派执行失败：{sub_result.summary}"
                    append_assistant_part(
                        run,
                        AssistantMessagePartV2(type="error", text=failure_message, status="failed"),
                    )
                    run.observation = ObservationV2(
                        source="agent.delegation",
                        status="error",
                        summary=failure_message,
                        payload={"delegation_target": target, "delegation_goal": goal[:200]},
                    )
                    self._finalize_run(
                        run=run,
                        session_id=session_id,
                        persist_messages=persist_messages,
                        message=failure_message,
                        status="failed",
                        replan_count=replan_count,
                        delegation_count=delegation_count,
                        trace_event="run_failed",
                        trace_detail=f"Delegation to {target} failed: {sub_result.summary}",
                    )
                    emitter.emit(
                        event="run.failed",
                        detail=failure_message,
                        observation=run.observation,
                        output_message=failure_message,
                        run_status="failed",
                        include_run=True,
                    )
                    return

            if agent_step.action == "fail":
                failure_message = (agent_step.response_message or "Agent reported an unrecoverable failure.").strip()
                append_assistant_part(
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
                    replan_count=replan_count,
                    delegation_count=delegation_count,
                    trace_event="run_failed",
                    trace_detail="Run failed because the planner explicitly returned fail.",
                )
                emitter.emit(
                    event="run.failed",
                    detail="Run failed because the planner explicitly returned fail.",
                    observation=run.observation,
                    output_message=failure_message,
                    run_status="failed",
                    include_run=True,
                )
                return

            raise_if_cancelled(cancellation_event)

            if not agent_step.tool_calls:
                failure_message = "Planner selected call_tools but returned no tool calls."
                append_assistant_part(
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
                    replan_count=replan_count,
                    delegation_count=delegation_count,
                    trace_event="run_failed",
                    trace_detail=failure_message,
                )
                emitter.emit(
                    event="run.failed",
                    detail=failure_message,
                    observation=run.observation,
                    output_message=failure_message,
                    run_status="failed",
                    include_run=True,
                )
                return

            replan_requested = False
            for tool_call in agent_step.tool_calls:
                raise_if_cancelled(cancellation_event)
                tool_result = self._executor.execute_tool_call(
                    run=run,
                    request_context=request_context,
                    tool_call=tool_call,
                    visible_tools=visible_tools,
                    visible_agents=visible_agents,
                    policy=policy,
                    event_emitter=emitter,
                    cancellation_event=cancellation_event,
                    user_id=user_id,
                )
                tool_history.append(tool_result["history_item"])
                observation = tool_result.get("observation")
                if isinstance(observation, ObservationV2):
                    run.observation = observation
                recent_messages = list(self._store.get_session(session_id).messages) if persist_messages else recent_messages
                last_task_digest = self._build_current_task_digest(run)
                if tool_result.get("approval_required"):
                    approval_message = str(tool_result["final_message"])
                    self._finalize_run(
                        run=run,
                        session_id=session_id,
                        persist_messages=persist_messages,
                        message=approval_message,
                        status="awaiting_approval",
                        replan_count=replan_count,
                        delegation_count=delegation_count,
                        trace_event="approval_required",
                        trace_detail=approval_message,
                    )
                    emitter.emit(
                        event="submission.approval_required",
                        detail=approval_message,
                        output_message=approval_message,
                        run_status="awaiting_approval",
                        include_run=True,
                    )
                    return
                if tool_result["blocked"]:
                    failure_message = str(tool_result["final_message"])
                    append_assistant_part(
                        run,
                        AssistantMessagePartV2(type="error", text=failure_message, status="blocked"),
                    )
                    self._finalize_run(
                        run=run,
                        session_id=session_id,
                        persist_messages=persist_messages,
                        message=failure_message,
                        status="failed",
                        replan_count=replan_count,
                        delegation_count=delegation_count,
                        trace_event="run_failed",
                        trace_detail="Run failed because a requested tool was blocked by policy.",
                    )
                    emitter.emit(
                        event="run.failed",
                        detail="Run failed because a requested tool was blocked by policy.",
                        observation=run.observation,
                        output_message=failure_message,
                        run_status="failed",
                        include_run=True,
                    )
                    return
                if isinstance(observation, ObservationV2) and observation.status == "error":
                    failure_message = str(tool_result["final_message"])
                    try:
                        self._guard.validate_replan(policy=policy, replan_count=replan_count)
                    except PolicyGuardError:
                        append_assistant_part(
                            run,
                            AssistantMessagePartV2(type="error", text=failure_message, status="failed"),
                        )
                        self._finalize_run(
                            run=run,
                            session_id=session_id,
                            persist_messages=persist_messages,
                            message=failure_message,
                            status="failed",
                            replan_count=replan_count,
                            delegation_count=delegation_count,
                            trace_event="run_failed",
                            trace_detail="Run failed after exhausting the replan budget.",
                        )
                        emitter.emit(
                            event="run.failed",
                            detail="Run failed after exhausting the replan budget.",
                            observation=run.observation,
                            output_message=failure_message,
                            run_status="failed",
                            include_run=True,
                        )
                        return
                    replan_count += 1
                    run.replan_count = replan_count
                    run.trace.append(TraceEventV2(
                        node="policy_guard",
                        event="replan_requested",
                        detail=f"Authorized replan {replan_count}/{policy.max_replans} after tool failure.",
                    ))
                    emitter.emit(
                        event="run.progress",
                        detail=f"Tool failed; replanning ({replan_count}/{policy.max_replans}).",
                        observation=observation,
                        run_status="running",
                    )
                    replan_requested = True
                    break

            if replan_requested:
                continue

            current_call_signature = observer.build_call_signature(agent_step.tool_calls or [])
            should_terminate, dup_count = observer.check_duplicate(current_call_signature)

            if should_terminate:
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
                    f"工具已连续重复调用 {dup_count + 1} 次，自动终止循环。\n\n"
                    f"最后一次工具结果摘要：\n{last_result_summary}"
                )
                append_assistant_part(
                    run,
                    AssistantMessagePartV2(type="text", text=response_message, status="completed"),
                )
                run.trace.append(
                    TraceEventV2(
                        node="runtime",
                        event="loop_terminated_duplicate_calls",
                        detail=f"Terminated after {dup_count + 1} consecutive identical tool calls.",
                    )
                )
                self._finalize_run(
                    run=run,
                    session_id=session_id,
                    persist_messages=persist_messages,
                    message=response_message,
                    status="completed",
                    replan_count=replan_count,
                    delegation_count=delegation_count,
                    trace_event="run_finalized",
                    trace_detail="Run finalized after detecting duplicate tool calls.",
                )
                emitter.emit(
                    event="assistant.delta",
                    detail="Auto-terminated duplicate tool call loop.",
                    output_message=response_message,
                    run_status="completed",
                )
                emitter.emit(
                    event="run.completed",
                    detail="Run completed after detecting duplicate tool calls.",
                    output_message=response_message,
                    run_status="completed",
                    include_run=True,
                )
                return

        _term_reason, failure_message = observer.check_max_steps()
        append_assistant_part(
            run,
            AssistantMessagePartV2(type="error", text=failure_message, status="failed"),
        )
        run.observation = ObservationV2(
            source="agent.runtime",
            status="error",
            summary=failure_message,
            payload={"max_steps": observer.max_steps},
        )
        self._finalize_run(
            run=run,
            session_id=session_id,
            persist_messages=persist_messages,
            message=failure_message,
            status="failed",
            replan_count=replan_count,
            delegation_count=delegation_count,
            trace_event="run_failed",
            trace_detail="Run failed because the max agent step budget was exceeded.",
        )
        emitter.emit(
            event="run.failed",
            detail="Run failed because the max agent step budget was exceeded.",
            observation=run.observation,
            output_message=failure_message,
            run_status="failed",
            include_run=True,
        )

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

    def _describe_llm_failure(self, error: AgentLLMError) -> str:
        if error.category == "upstream_overloaded":
            return f"Upstream LLM unavailable or overloaded during structured planning: {error}"
        if error.category == "incomplete_generation":
            return f"Upstream LLM returned incomplete structured output during planning: {error}"
        if error.category == "schema_mismatch":
            return f"Upstream LLM returned a schema-mismatched planner step: {error}"
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
        # ── LLM-driven PROSAIL scene parameter extraction ──
        _lai_kw = {"lai", "leaf area", "叶面积", "prosail"}
        if context.image_path and (
            context.task_type == "lai_inversion"
            or any(kw in user_message.lower() for kw in _lai_kw)
        ):
            try:
                from v2.runtime.scene_extractor import extract_scene_parameters as _extract

                context.scene_parameters = _extract(
                    llm_provider=self._llm_provider,
                    query=user_message,
                    image_path=context.image_path,
                    region=context.region,
                    crop_type=context.crop_type,
                )
                if context.scene_parameters.confidence < 0.4:
                    logger.warning(
                        "scene_parameters_low_confidence | "
                        "confidence=%s task_type=%s region=%s",
                        context.scene_parameters.confidence,
                        context.task_type,
                        context.region,
                    )
            except Exception:
                logger.exception("scene_parameters_extraction_failed")
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
            allowed_categories = {"analysis", "knowledge", "report", "visualization", "training", "crop_simulation", "remote_sensing", "workspace"}
        visible_tools = []
        for tool in self._tool_registry.list_tools():
            if not tool.enabled_by_default and tool.surface_visibility not in {"debug", "internal"}:
                continue
            if request_context.entrypoint in {"chat", "v2_ui", "api", "detect"}:
                if tool.surface_visibility not in {"all", "web", "api"}:
                    continue
            if allowed_categories is not None and tool.category not in allowed_categories:
                continue
            visible_tools.append(tool)
        return visible_tools

    @staticmethod
    def _build_last_task_digest(previous_run: RunDetail | None) -> dict[str, object] | None:
        if previous_run is None:
            return None
        # Phase B.3: prefer the persisted task_digest from _finalize_run();
        # fall back to computing from tool_invocations for runs saved before this phase.
        if previous_run.task_digest:
            return previous_run.task_digest
        if not previous_run.tool_invocations:
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

    # Phase B.2 supplement: LLM-driven fact extraction from successful exchanges.
    def _extract_facts_from_exchange(
        self,
        *,
        user_message: str,
        assistant_response: str,
    ) -> list[dict[str, str]]:
        """Extract 0-3 notable facts from a completed user↔assistant exchange.

        Uses the LLM to identify generalizable knowledge worth persisting
        (user preferences, domain knowledge, project conventions, etc.).
        Returns a list of dicts with keys: name, description, type, body.
        Returns an empty list when nothing noteworthy is found or on error.
        """
        if not user_message or not assistant_response:
            return []

        prompt = (
            "从以下用户提问和AI助手的对话中提取值得记住的事实。\n"
            "只提取那些对未来对话有参考价值的、可泛化的事实，例如：\n"
            "- 用户的个人偏好或工作习惯\n"
            "- 项目中使用的具体技术、配置或约定\n"
            "- 特定遥感领域的知识\n"
            "- 对后续对话有参考价值的决策\n\n"
            "标准闲聊、问候、确认等不需要提取。\n\n"
            "请以 JSON 数组格式输出，每个元素包含：\n"
            '- name: 短横线命名，英文，如 "user-prefers-chinese-output"\n'
            "- description: 一行中文描述\n"
            "- type: 类型，可选 user / project / domain / feedback\n"
            "- body: 具体的事实内容（中文，2-5 句话）\n\n"
            "如果没有任何值得记住的事实，返回空数组 []。\n"
            "只返回 JSON，不要其他内容。"
        )
        user_prompt = f"用户：{user_message}\n\n助手：{assistant_response}"

        try:
            raw = self._llm_provider.generate_text(
                system_prompt=prompt,
                user_prompt=user_prompt,
                max_tokens=512,
            )
            raw = raw.strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                first_nl = raw.find("\n")
                if first_nl != -1:
                    raw = raw[first_nl + 1:]
                if raw.endswith("```"):
                    raw = raw[:-3].strip()
                elif "```" in raw:
                    raw = raw.rsplit("```", 1)[0].strip()
            facts: list[dict[str, str]] = json.loads(raw)
            if not isinstance(facts, list):
                return []
            valid: list[dict[str, str]] = []
            for f in facts:
                if isinstance(f, dict) and all(k in f for k in ("name", "description", "body")):
                    valid.append(f)
            return valid[:3]
        except Exception as exc:
            logger.warning("_extract_facts_from_exchange failed: %s", exc)
            return []

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
    def _finalize_run(
        self,
        *,
        run: RunDetail,
        session_id: str,
        persist_messages: bool,
        message: str,
        status: RuntimeRunStatus,
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
        # Phase B.3: persist task digest so the next run can skip recomputing from tool_invocations
        run.task_digest = self._build_current_task_digest(run)
        # Phase B.2 supplement: extract and persist notable facts from completed runs.
        if (
            status == "completed"
            and self._memory_manager is not None
            and self._memory_manager.is_loaded
            and self._memory_auto_write_enabled
            and run.input_message
        ):
            facts = self._extract_facts_from_exchange(
                user_message=run.input_message,
                assistant_response=message,
            )
            for fact in facts:
                self._memory_manager.write_fact(
                    name=str(fact.get("name", "")),
                    description=str(fact.get("description", "")),
                    body=str(fact.get("body", "")),
                    metadata={"type": fact.get("type", "feedback"), "source": "agent_extraction"},
                )
