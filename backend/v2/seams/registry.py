"""Seam provider registry.

The registry binds one capability name to one provider implementation and
validates the provider structurally against the seam protocol. It is the
single place where "which implementation backs this capability" is declared,
so startup can fail loud instead of discovering a mismatch on first use.

This is the V2 equivalent of a DeepSeek Harness capability seam registry,
minus the plugin tree: registrations are plain Python objects, there is no
dynamic reload, and the caller decides when to build the registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from v2.seams.protocols import (
    ArtifactSeam,
    DatasetSeam,
    LLMSeam,
    MemorySeam,
    ToolSeam,
)


class SeamError(RuntimeError):
    """A seam could not be registered or resolved."""


#: Capability name -> protocol that a provider must satisfy.
CAPABILITY_PROTOCOLS: Mapping[str, type] = {
    "llm": LLMSeam,
    "datasets": DatasetSeam,
    "artifacts": ArtifactSeam,
    "memory": MemorySeam,
    "tools": ToolSeam,
}

#: Capability name -> required callable members, used for actionable errors.
CAPABILITY_METHODS: Mapping[str, tuple[str, ...]] = {
    "llm": ("generate_text", "generate_structured"),
    "datasets": ("resolve",),
    "artifacts": ("register", "get", "list_by_run", "list_all"),
    "memory": (
        "reload",
        "entries",
        "is_loaded",
        "get",
        "find_relevant",
        "build_context_injection",
    ),
    "tools": (
        "list_tools",
        "get_definition",
        "has_tool",
        "register",
        "unregister",
        "invoke",
        "invoke_algorithm",
    ),
}


@dataclass(frozen=True)
class SeamProvider:
    """One capability implementation."""

    capability: str
    name: str
    implementation: Any


class SeamRegistry:
    """Binds capability names to validated provider implementations."""

    def __init__(self) -> None:
        self._providers: dict[str, SeamProvider] = {}

    def register(self, capability: str, name: str, implementation: Any) -> SeamProvider:
        """Register one provider, rejecting unknown capabilities and duplicates."""
        protocol = CAPABILITY_PROTOCOLS.get(capability)
        if protocol is None:
            raise SeamError(
                f"unknown capability {capability!r}; known: {sorted(CAPABILITY_PROTOCOLS)}"
            )
        if capability in self._providers:
            existing = self._providers[capability]
            raise SeamError(
                f"capability {capability!r} is already registered by {existing.name!r}"
            )
        if implementation is None:
            raise SeamError(f"capability {capability!r} requires an implementation")
        missing = [
            method
            for method in CAPABILITY_METHODS[capability]
            if not callable(getattr(implementation, method, None))
        ]
        if missing:
            raise SeamError(
                f"provider {name!r} for capability {capability!r} is missing "
                f"{missing}; it must satisfy {protocol.__name__}"
            )
        provider = SeamProvider(capability=capability, name=name, implementation=implementation)
        self._providers[capability] = provider
        return provider

    def get(self, capability: str) -> SeamProvider:
        """Return the provider for ``capability`` or fail loud."""
        provider = self._providers.get(capability)
        if provider is None:
            raise SeamError(
                f"capability {capability!r} has no provider; registered: "
                f"{sorted(self._providers)}"
            )
        return provider

    def has(self, capability: str) -> bool:
        """Whether ``capability`` has a provider."""
        return capability in self._providers

    def capabilities(self) -> list[str]:
        """Return registered capability names in stable order."""
        return sorted(self._providers)

    def describe(self) -> dict[str, str]:
        """Return capability -> provider name for diagnostics and manifests."""
        return {name: provider.name for name, provider in sorted(self._providers.items())}

    def missing(self, required: list[str] | tuple[str, ...]) -> list[str]:
        """Return the required capabilities that have no provider."""
        return [capability for capability in required if capability not in self._providers]


def build_default_seams(
    *,
    llm: Any = None,
    datasets: Any = None,
    artifacts: Any = None,
    memory: Any = None,
    tools: Any = None,
) -> SeamRegistry:
    """Build the default seam registry from the runtime's existing objects.

    ``None`` means "this deployment does not provide the capability"; a
    composition that requires it will fail validation instead of degrading
    silently.
    """
    registry = SeamRegistry()
    for capability, name, implementation in (
        ("llm", "agent-llm", llm),
        ("datasets", "algorithm-dataset-resolver", datasets),
        ("artifacts", "sqlite-artifact-store", artifacts),
        ("memory", "markdown-memory", memory),
        ("tools", "v2-tool-registry", tools),
    ):
        if implementation is not None:
            registry.register(capability, name, implementation)
    return registry
