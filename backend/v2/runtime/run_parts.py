"""Single point for assistant-message part appends.

Extracted so middleware and the executor can share the helper without an
import cycle.
"""

from __future__ import annotations

from schemas.runtime import AssistantMessagePartV2, AssistantMessageV2, RunDetail


def append_assistant_part(run: RunDetail, part: AssistantMessagePartV2) -> None:
    """Append a part to the run's assistant message."""
    if run.assistant_message is None:
        run.assistant_message = AssistantMessageV2(parts=[])
    run.assistant_message.parts.append(part)
