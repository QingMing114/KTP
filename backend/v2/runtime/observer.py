"""Run observer for the V2 bounded runtime.

Extracted from BoundedRuntimeEngine._execute_agent_loop — encapsulates
duplicate-call detection, tool-result termination checks, and max-steps
enforcement so the engine loop stays thin.

Modeled after Claude Code's Observer: validates each observation and
decides whether to replan, terminate, or continue.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from schemas.runtime import AgentToolCallV2

logger = logging.getLogger(__name__)


class RunObserver:
    """Validates observations and enforces loop termination rules.

    Extracted from ``BoundedRuntimeEngine._execute_agent_loop()``:
    the duplicate-call detector, tool-error bail-out, and max-steps guard.

    Usage inside the agent loop::

        observer = RunObserver(max_steps=20)

        for step_index in range(max_steps):
            # ... planner produces agent_step ...
            # ... executor runs tool calls ...

            for tool_result in tool_results:
                reason = observer.should_terminate_after_tool(tool_result)
                if reason is not None:
                    # emit events, finalize, return

            sig = observer.build_call_signature(agent_step.tool_calls)
            terminate, count = observer.check_duplicate(sig)
            if terminate:
                # emit events, finalize, return

        # After loop
        reason, message = observer.check_max_steps()
        if reason:
            # emit events, finalize, return
    """

    def __init__(self, *, max_steps: int) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be >= 1")
        self.max_steps = max_steps
        self._consecutive_replan_count = 0
        self._last_tool_call_signature: str | None = None
        self._steps_taken = 0

    # ── call-signature / duplicate detection ──

    @staticmethod
    def build_call_signature(tool_calls: list[AgentToolCallV2]) -> str:
        """Build a stable, sort-keyed signature from tool calls for dedup.

        When consecutive iterations produce the identical signature the
        agent is stuck in a loop — the observer signals termination.
        """
        return "|".join(
            f"{tc.tool_name}:{json.dumps(tc.tool_input, sort_keys=True, default=str)}"
            for tc in tool_calls
        )

    def check_duplicate(
        self, current_signature: str
    ) -> tuple[bool, int]:
        """Check if the current call signature is a duplicate of the last.

        Returns ``(should_terminate, consecutive_replan_count)``.
        Termination fires after **2** consecutive identical calls
        (i.e. ``consecutive_replan_count >= 1`` matches original engine
        behaviour).

        Call this once per agent loop iteration *after* all tool results
        have been processed.
        """
        if current_signature == self._last_tool_call_signature:
            self._consecutive_replan_count += 1
        else:
            self._consecutive_replan_count = 0
        self._last_tool_call_signature = current_signature
        self._steps_taken += 1

        if self._consecutive_replan_count >= 1:
            return True, self._consecutive_replan_count
        return False, self._consecutive_replan_count

    # ── tool-result checks ──

    @staticmethod
    def should_terminate_after_tool(tool_result: dict[str, object]) -> str | None:
        """Return a termination reason if the tool result warrants stopping.

        Reasons:

        * ``"tool_blocked"`` — permission gate denied execution
        * ``"tool_error"`` — tool returned an error observation

        Returns ``None`` when the loop should continue normally.
        """
        observation = tool_result.get("observation")
        if observation is None:
            return None

        # blocked tools
        if tool_result.get("blocked"):
            return "tool_blocked"

        # error observations
        if hasattr(observation, "status") and observation.status == "error":
            return "tool_error"

        return None

    # ── post-loop max-steps guard ──

    def check_max_steps(
        self, *, completed: bool = False
    ) -> tuple[str | None, str]:
        """Check whether the agent exhausted its step budget.

        Call this *after* the ``for step_index in range(max_steps)`` loop
        when no early-return fired.

        Returns ``(termination_reason, failure_message)``.
        ``termination_reason`` is ``None`` when the run completed normally.
        """
        if completed:
            return None, ""

        failure_message = (
            f"Agent reached max steps ({self.max_steps}) without producing a final reply. "
            f"Increase AGENT_LLM_AGENT_MAX_STEPS or check if the task is too complex."
        )
        return "max_steps_exceeded", failure_message

    # ── helpers ──

    @property
    def consecutive_replan_count(self) -> int:
        """How many times the agent has issued the same tool calls in a row."""
        return self._consecutive_replan_count

    @property
    def steps_taken(self) -> int:
        """How many loop iterations have been observed so far."""
        return self._steps_taken

    def reset(self) -> None:
        """Reset all counters (useful for replay)."""
        self._consecutive_replan_count = 0
        self._last_tool_call_signature = None
        self._steps_taken = 0
