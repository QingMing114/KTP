"""Asynchronous subagent runtime.

M1 of the multi-agent rollout: spawn is immediate, the child runs on its own
thread with an isolated planner loop and a role-restricted tool subset, and the
result is delivered as a settlement into the parent inbox. The parent keeps
planning while children run and drains settlements at its step boundary.

Deliberately out of scope here: nested delegation by children (children get
``allow_delegation=False``), cross-process scheduling, and persistent transcripts
for child runs beyond the parent's run record.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from threading import Event
from typing import TYPE_CHECKING, Any

from schemas.runtime import AgentProfile, PermissionPolicy, RequestContextV2, RunDetail

from v2.agents.inbox import AgentInbox, AgentSettlement

if TYPE_CHECKING:
    from infra.llm.provider import AgentLLMProvider
    from v2.runtime.events import RunEventEmitter
    from v2.tools.registry import ToolRegistryV2

logger = logging.getLogger(__name__)

MAX_DEPTH = 1
DEFAULT_MAX_CHILDREN = 3
DEFAULT_TIMEOUT_SECONDS = 120.0


class SubAgentError(RuntimeError):
    """Raised when a spawn request violates a limit."""


@dataclass
class AgentHandle:
    agent_run_id: str
    parent_run_id: str
    role: str
    goal: str
    started_at: float = field(default_factory=time.monotonic)


class SubAgentRuntime:
    """Spawns and settles child agents for one parent run at a time."""

    def __init__(
        self,
        *,
        tool_registry: "ToolRegistryV2",
        llm_provider: "AgentLLMProvider | None",
        profile_registry: Any,
        inbox: AgentInbox | None = None,
        max_concurrent_children: int = DEFAULT_MAX_CHILDREN,
        default_timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._tool_registry = tool_registry
        self._llm_provider = llm_provider
        self._profiles = profile_registry
        self._inbox = inbox or AgentInbox()
        self._max_children = max_concurrent_children
        self._timeout = default_timeout_seconds
        self._lock = threading.Lock()
        self._active: dict[str, list[AgentHandle]] = {}
        self._cancellations: dict[str, Event] = {}

    @property
    def inbox(self) -> AgentInbox:
        return self._inbox

    def profile_for(self, role: str) -> AgentProfile:
        for profile in self._profiles.list_profiles():
            if profile.name == role or profile.role == role:
                return profile
        raise SubAgentError(f"unknown agent role: {role}")

    def spawn(
        self,
        *,
        parent_run: RunDetail,
        parent_emitter: "RunEventEmitter",
        request_context: RequestContextV2,
        role: str,
        goal: str,
        policy: PermissionPolicy,
        user_id: str | None = None,
        granted_permissions: set[str] | frozenset[str] | None = None,
        cancellation_event: Event | None = None,
        depth: int = MAX_DEPTH,
    ) -> AgentHandle:
        if depth > MAX_DEPTH:
            raise SubAgentError("嵌套委派超出深度上限")
        profile = self.profile_for(role)
        if profile.role == "planner":
            raise SubAgentError(f"{profile.name} 不能作为子代理目标")
        with self._lock:
            active = self._active.setdefault(parent_run.run_id, [])
            if len(active) >= self._max_children:
                raise SubAgentError(f"并发子代理已达上限（{self._max_children}）")
            handle = AgentHandle(
                agent_run_id=str(uuid.uuid4()),
                parent_run_id=parent_run.run_id,
                role=profile.name,
                goal=goal,
            )
            active.append(handle)
            child_cancel = _child_cancellation(cancellation_event)
            self._cancellations.setdefault(parent_run.run_id, []).append(child_cancel)
        parent_emitter.emit(
            event="run.progress",
            detail=f"已激活子代理 {profile.name}（{handle.agent_run_id[:8]}）：{goal[:80]}",
            run_status="running",
        )
        thread = threading.Thread(
            target=self._run_child,
            kwargs={
                "handle": handle,
                "profile": profile,
                "policy": policy,
                "request_context": request_context,
                "parent_run": parent_run,
                "parent_emitter": parent_emitter,
                "cancellation_event": child_cancel,
                "user_id": user_id,
                "granted_permissions": granted_permissions,
            },
            daemon=True,
            name=f"subagent-{profile.name}-{handle.agent_run_id[:8]}",
        )
        thread.start()
        return handle

    def _run_child(
        self,
        *,
        handle: AgentHandle,
        profile: AgentProfile,
        policy: PermissionPolicy,
        request_context: RequestContextV2,
        parent_run: RunDetail,
        parent_emitter: "RunEventEmitter",
        cancellation_event: Event | None,
        user_id: str | None,
        granted_permissions: set[str] | frozenset[str] | None,
    ) -> None:
        started = time.monotonic()
        success = False
        summary = ""
        error: str | None = None
        artifacts: list[Any] = []
        tool_invocations: list[Any] = []
        try:
            from v2.runtime.sub_executor import SubExecutor

            # Always build a subset: an empty prefix list means "no tools",
            # which is how a review-only role stays read-only.
            registry = self._tool_registry.subset_by_prefixes(list(profile.tool_prefixes))
            child_cancel = cancellation_event
            sub = SubExecutor(
                tool_registry=registry,
                llm_provider=self._llm_provider,
                policy=policy,
                cancellation_event=child_cancel,
                user_id=user_id,
                granted_permissions=granted_permissions,
                system_prompt_suffix=profile.system_prompt,
                max_steps=profile.max_steps,
            )
            result = sub.execute(
                goal=handle.goal,
                request_context=request_context,
                parent_emitter=parent_emitter,
                parent_run=parent_run,
            )
            success = result.success
            summary = result.summary
            artifacts = list(result.artifacts)
            tool_invocations = list(result.tool_invocations)
        except Exception as exc:  # child failure must never crash the parent
            logger.exception("subagent_failed | role=%s run=%s", profile.name, handle.agent_run_id)
            error = f"{type(exc).__name__}: {exc}"
            summary = f"子代理执行异常：{exc}"
        finally:
            self._finish(handle, success=success, summary=summary, error=error,
                         duration=time.monotonic() - started,
                         artifact_count=len(artifacts), tool_count=len(tool_invocations))

    def _finish(
        self,
        handle: AgentHandle,
        *,
        success: bool,
        summary: str,
        error: str | None,
        duration: float,
        artifact_count: int,
        tool_count: int,
    ) -> None:
        with self._lock:
            active = self._active.get(handle.parent_run_id, [])
            self._active[handle.parent_run_id] = [h for h in active if h.agent_run_id != handle.agent_run_id]
        self._inbox.push(
            AgentSettlement(
                agent_run_id=handle.agent_run_id,
                parent_run_id=handle.parent_run_id,
                role=handle.role,
                goal=handle.goal,
                success=success,
                summary=summary,
                duration_seconds=round(duration, 3),
                artifact_count=artifact_count,
                tool_count=tool_count,
                error=error,
            )
        )

    def pending(self, parent_run_id: str) -> int:
        with self._lock:
            return len(self._active.get(parent_run_id, ()))

    def drain(self, parent_run_id: str) -> list[AgentSettlement]:
        return self._inbox.drain(parent_run_id)

    def wait_for_settlements(
        self, parent_run_id: str, timeout_seconds: float | None = None
    ) -> list[AgentSettlement]:
        return self._inbox.wait(parent_run_id, timeout_seconds or self._timeout)

    def cancel(self, parent_run_id: str) -> None:
        with self._lock:
            events = self._cancellations.pop(parent_run_id, [])
        for event in events:
            event.set()


def _child_cancellation(parent: Event | None) -> Event:
    """Each child gets its own event; it is not shared with siblings."""
    child = Event()
    if parent is not None:
        def _bridge() -> None:
            while not parent.wait(0.1):
                if child.is_set():
                    return
            child.set()

        threading.Thread(target=_bridge, daemon=True).start()
    return child
