"""Explicit composition manifest for the V2 runtime.

The manifest is the single readable answer to "which capabilities and tools are
wired in this deployment". It replaces the need to read the tool registry
literal or the engine's visibility whitelist to understand the composition.

Deliberate differences from a DeepSeek Harness profile: one flat layer, no patch
merging, no hot reload. Changing composition requires a restart and the normal
acceptance flow.
"""

from __future__ import annotations

from typing import Iterable, Literal

from pydantic import BaseModel, Field

from v2.seams.registry import CAPABILITY_PROTOCOLS, SeamError, SeamRegistry


class CompositionError(RuntimeError):
    """The composition manifest is inconsistent with the runtime."""


class ToolExposure(BaseModel):
    """How registered tools are exposed to each surface."""

    default: Literal["model", "workflow", "endpoint"] = "model"
    disabled: list[str] = Field(default_factory=list)
    endpoint_only: list[str] = Field(default_factory=list)


class CompositionSpec(BaseModel):
    """One deployment's composition declaration."""

    name: str = "ktp-default"
    required_capabilities: list[str] = Field(default_factory=lambda: ["tools"])
    optional_capabilities: list[str] = Field(
        default_factory=lambda: ["llm", "datasets", "artifacts", "memory"]
    )
    tools: ToolExposure = Field(default_factory=ToolExposure)


def build_default_composition() -> CompositionSpec:
    """Return the composition used by the current single-tenant deployment."""
    return CompositionSpec()


def validate_composition(
    spec: CompositionSpec,
    *,
    seams: SeamRegistry,
    tool_names: Iterable[str],
) -> list[str]:
    """Validate ``spec`` against the seam registry and registered tools.

    Returns warnings for discoverability gaps (tools present but unmentioned).
    Raises :class:`CompositionError` for configuration errors: unknown
    capabilities, missing required capabilities, misspelled tool names, or a
    tool listed as both disabled and endpoint-only.
    """
    known_capabilities = set(CAPABILITY_PROTOCOLS)
    declared = set(spec.required_capabilities) | set(spec.optional_capabilities)
    unknown = sorted(declared - known_capabilities)
    if unknown:
        raise CompositionError(
            f"composition {spec.name!r} declares unknown capabilities {unknown}; "
            f"known: {sorted(known_capabilities)}"
        )

    missing = seams.missing(spec.required_capabilities)
    if missing:
        raise CompositionError(
            f"composition {spec.name!r} requires capabilities without providers "
            f"{missing}; registered: {seams.capabilities()}"
        )

    registered = set(tool_names)
    declared_tools = set(spec.tools.disabled) | set(spec.tools.endpoint_only)
    unknown_tools = sorted(declared_tools - registered)
    if unknown_tools:
        raise CompositionError(
            f"composition {spec.name!r} references unregistered tools "
            f"{unknown_tools}; registered tools: {sorted(registered)}"
        )

    overlap = sorted(set(spec.tools.disabled) & set(spec.tools.endpoint_only))
    if overlap:
        raise CompositionError(
            f"composition {spec.name!r} lists tools as both disabled and "
            f"endpoint-only: {overlap}"
        )

    unmentioned = sorted(registered - declared_tools)
    if unmentioned:
        return [
            f"composition {spec.name!r} does not mention registered tools "
            f"{unmentioned}; they follow the default exposure "
            f"{spec.tools.default!r}"
        ]
    return []


def resolve_seam(seams: SeamRegistry, capability: str):
    """Return one seam implementation or raise a composition-level error."""
    try:
        return seams.get(capability).implementation
    except SeamError as exc:  # pragma: no cover - defensive translation
        raise CompositionError(str(exc)) from exc
