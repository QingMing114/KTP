"""Ordered tool-execution pipeline.

Stages: ``before`` middlewares -> ``dispatch`` -> ``finalize`` -> ``after``
middlewares. The pipeline itself holds no policy; behavior is defined by the
composed middlewares, and registration order is execution order.

Deliberate simplifications versus a DeepSeek Harness tool pipeline: one ordered
chain (not three typed event domains), synchronous only, and no dynamic
middleware installation at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, Sequence, runtime_checkable


@dataclass
class ToolCallState:
    """Everything one tool call needs, plus everything it produced."""

    # Inputs
    run: Any
    request_context: Any
    tool_call: Any
    spec: Any
    policy: Any
    visible_tools: Any
    visible_agents: Any
    event_emitter: Any
    cancellation_event: Any = None
    user_id: str | None = None
    granted_permissions: Any = None

    # Preparation output
    invocation: Any = None

    # Dispatch output
    observation: Any = None
    artifacts: list[Any] = field(default_factory=list)
    final_message: str = ""
    macro_invocation_index: int | None = None
    skip_dispatch: bool = False


@runtime_checkable
class ToolMiddleware(Protocol):
    """A stage around tool dispatch."""

    name: str

    def before(self, state: ToolCallState) -> dict[str, object] | None:
        """Run before dispatch.

        Return a result payload to short-circuit the call (for example a
        blocked or approval-required result), or ``None`` to continue.
        """

    def after(self, state: ToolCallState) -> None:
        """Run after finalize, observing the settled state."""


DispatchFn = Callable[[ToolCallState], None]
FinalizeFn = Callable[[ToolCallState], None]


class ToolPipeline:
    """Composes middlewares around one dispatch and one finalize function."""

    def __init__(
        self,
        *,
        before: Sequence[ToolMiddleware] = (),
        after: Sequence[ToolMiddleware] = (),
    ) -> None:
        self._before = tuple(before)
        self._after = tuple(after)
        names = [middleware.name for middleware in (*self._before, *self._after)]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate tool middleware names: {names}")

    @property
    def middleware_names(self) -> list[str]:
        """Return registered middleware names in execution order."""
        return [middleware.name for middleware in (*self._before, *self._after)]

    def run(
        self,
        state: ToolCallState,
        *,
        dispatch: DispatchFn,
        finalize: FinalizeFn,
    ) -> dict[str, object] | None:
        """Run the call and return an early result payload when short-circuited."""
        for middleware in self._before:
            early = middleware.before(state)
            if early is not None:
                return early

        if not state.skip_dispatch:
            dispatch(state)
        finalize(state)

        for middleware in self._after:
            middleware.after(state)
        return None
