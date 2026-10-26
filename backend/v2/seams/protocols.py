"""Capability seams for the V2 runtime.

A seam is a replaceable capability with three roles: a Service Definition (the
protocol here), one or more Service Providers (existing concrete classes), and
one or more Consumers (engine, planner, executor, routes).

This module defines only the Definitions. It intentionally does not move the
current implementations: providers stay where they are and are validated
structurally, so introducing a seam cannot change runtime behavior.

Design notes live in ``docs/tool_seam_v1_design.md``.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMSeam(Protocol):
    """Provider contract for planner/executor generations."""

    def generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int | None = None,
    ) -> str:
        """Generate a free-form text response."""

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[Any],
    ) -> Any:
        """Generate a response validated against ``response_model``."""


@runtime_checkable
class DatasetSeam(Protocol):
    """Resolve model-provided dataset references against trusted context."""

    def resolve(
        self,
        tool_input: Any,
        execution_context: Any,
        *,
        allowed_suffixes: set[str] | None = None,
        allowed_media_types: set[str] | None = None,
        max_bytes: int | None = None,
        required_roles: set[str] | None = None,
    ) -> list[Any]:
        """Return resolved datasets or raise a typed algorithm error."""


@runtime_checkable
class ArtifactSeam(Protocol):
    """Register and read run artifacts."""

    def register(self, run_id: str, artifact: Any) -> str:
        """Persist one artifact and return its id."""

    def get(self, artifact_id: str) -> Any | None:
        """Return one artifact record, or ``None`` when absent."""

    def list_by_run(self, run_id: str) -> list[Any]:
        """Return artifacts registered for one run."""

    def list_all(self) -> list[Any]:
        """Return every registered artifact record."""


@runtime_checkable
class MemorySeam(Protocol):
    """Read structured markdown memory and build prompt injections."""

    def reload(self) -> None:
        """Reload memory entries from disk."""

    def entries(self) -> dict[str, Any]:
        """Return loaded entries keyed by name."""

    def is_loaded(self) -> bool:
        """Whether memory has been loaded at least once."""

    def get(self, name: str) -> Any | None:
        """Return one entry by name."""

    def find_relevant(self, query: str, *, top_k: int = 5) -> list[Any]:
        """Return entries ranked by relevance to ``query``."""

    def build_context_injection(
        self,
        query: str,
        *,
        top_k: int = 5,
        max_chars: int = 2000,
    ) -> str:
        """Return the formatted prompt fragment for relevant entries."""


@runtime_checkable
class ToolSeam(Protocol):
    """Tool registry and dispatch surface used by the runtime."""

    def list_tools(self) -> list[Any]:
        """Return every registered tool spec."""

    def get_definition(self, tool_name: str) -> Any:
        """Return the definition for ``tool_name``."""

    def has_tool(self, tool_name: str) -> bool:
        """Whether ``tool_name`` is registered."""

    def register(self, name: str, spec: Any, handler: Any) -> None:
        """Register one tool spec and handler."""

    def unregister(self, name: str) -> bool:
        """Remove one tool registration."""

    def invoke(
        self,
        *,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> Any:
        """Invoke a legacy or plain tool by name."""

    def invoke_algorithm(
        self,
        *,
        tool_name: str,
        tool_input: dict[str, Any],
        execution_context: Any,
        execution_control: Any,
    ) -> Any:
        """Invoke one ``algorithm-tool/v1`` tool with runtime context."""
