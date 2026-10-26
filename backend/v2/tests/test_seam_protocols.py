"""Seam protocol conformance tests.

These lock the contract that the existing providers satisfy the seam
Definitions. They do not change runtime behavior; they make a provider swap
fail loudly at the seam boundary instead of at first use.
"""

from __future__ import annotations

import pytest

from runtime.artifact_store import ArtifactStore
from v2.runtime.memory_manager import MemoryManager
from v2.seams import (
    ArtifactSeam,
    DatasetSeam,
    LLMSeam,
    MemorySeam,
    SeamError,
    SeamRegistry,
    ToolSeam,
    build_default_seams,
)
from v2.tools.registry import ToolRegistryV2
from v2.tools.remote_sensing.dataset_resolver import AlgorithmDatasetResolver


class _StubLLM:
    def generate_text(self, *, system_prompt: str, user_prompt: str, max_tokens: int | None = None) -> str:
        return ""

    def generate_structured(self, *, system_prompt: str, user_prompt: str, response_model):
        return response_model()


def test_existing_providers_satisfy_their_seams(tmp_path):
    assert isinstance(AlgorithmDatasetResolver(), DatasetSeam)
    assert isinstance(ArtifactStore(str(tmp_path / "artifacts.sqlite3")), ArtifactSeam)
    assert isinstance(MemoryManager(memory_dir=tmp_path), MemorySeam)
    assert isinstance(ToolRegistryV2(definitions={}), ToolSeam)
    assert isinstance(_StubLLM(), LLMSeam)


def test_scalar_object_does_not_satisfy_a_seam():
    assert not isinstance(object(), ToolSeam)
    assert not isinstance(object(), LLMSeam)


def test_register_rejects_unknown_duplicate_and_incomplete_providers():
    registry = SeamRegistry()

    with pytest.raises(SeamError, match="unknown capability"):
        registry.register("telepathy", "x", object())

    with pytest.raises(SeamError, match="requires an implementation"):
        registry.register("tools", "x", None)

    with pytest.raises(SeamError, match="is missing"):
        registry.register("tools", "broken", object())

    registry.register("tools", "ok", ToolRegistryV2(definitions={}))
    with pytest.raises(SeamError, match="already registered"):
        registry.register("tools", "again", ToolRegistryV2(definitions={}))


def test_build_default_seams_skips_absent_capabilities():
    registry = build_default_seams(tools=ToolRegistryV2(definitions={}))

    assert registry.capabilities() == ["tools"]
    assert registry.has("tools")
    assert not registry.has("llm")
    assert registry.missing(["tools", "llm"]) == ["llm"]
    assert registry.describe() == {"tools": "v2-tool-registry"}

    with pytest.raises(SeamError, match="has no provider"):
        registry.get("llm")


def test_seam_registry_resolves_the_registered_implementation():
    tools = ToolRegistryV2(definitions={})
    registry = build_default_seams(tools=tools)

    assert registry.get("tools").implementation is tools
