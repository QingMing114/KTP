from __future__ import annotations

import logging
import re
import threading
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException

from v2.shared.schemas import ToolSpecV2
from v2.tools.plugin_adapter import PluginToolSpec, make_plugin_handler

if TYPE_CHECKING:
    from v2.tools.registry import ToolRegistryV2

logger = logging.getLogger(__name__)

_TOOL_NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.\-]{1,63}$")


def _validate_tool_name(name: str) -> None:
    if not _TOOL_NAME_PATTERN.match(name):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid tool name '{name}'. Must match pattern [a-zA-Z][a-zA-Z0-9_.-]{{1,63}}",
        )

router = APIRouter(prefix="/v2/plugins", tags=["plugins"])

_registry_ref: ToolRegistryV2 | None = None
_registry_lock = threading.Lock()


def set_registry(registry: ToolRegistryV2) -> None:
    global _registry_ref
    with _registry_lock:
        _registry_ref = registry


def _get_registry() -> ToolRegistryV2:
    with _registry_lock:
        if _registry_ref is None:
            raise RuntimeError("Plugin registry not initialized")
        return _registry_ref


@router.post("/tools", response_model=dict)
def register_plugin_tool(spec: PluginToolSpec) -> dict:
    _validate_tool_name(spec.name)
    registry = _get_registry()
    if registry.has_tool(spec.name):
        raise HTTPException(status_code=409, detail=f"Tool '{spec.name}' already registered")
    handler = make_plugin_handler(spec)
    tool_spec = ToolSpecV2(
        name=spec.name,
        display_name=spec.display_name or spec.name,
        description=spec.description,
        visibility="public",
        category=spec.category,
        pack_name=spec.pack_name,
        usage_hint=spec.usage_hint,
        input_schema=spec.input_schema,
        safety_level=spec.safety_level,
        surface_visibility="web",
        enabled_by_default=spec.enabled,
        capabilities=["plugin"],
    )
    registry.register(spec.name, tool_spec, handler)
    logger.info("Plugin tool registered: %s (adapter=%s)", spec.name, spec.endpoint.adapter)
    return {"status": "ok", "name": spec.name, "adapter": spec.endpoint.adapter}


@router.delete("/tools/{tool_name}", response_model=dict)
def unregister_plugin_tool(tool_name: str) -> dict:
    _validate_tool_name(tool_name)
    registry = _get_registry()
    if not registry.unregister(tool_name):
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
    logger.info("Plugin tool unregistered: %s", tool_name)
    return {"status": "ok", "name": tool_name}


@router.get("/tools", response_model=list[dict])
def list_plugin_tools() -> list[dict]:
    registry = _get_registry()
    all_tools = registry.list_tools()
    return [
        {"name": t.name, "display_name": t.display_name, "category": t.category, "pack_name": t.pack_name}
        for t in all_tools
        if t.category == "plugin" or (t.capabilities and "plugin" in t.capabilities)
    ]


@router.post("/tools/{tool_name}/test", response_model=dict)
def test_plugin_tool(tool_name: str, tool_input: dict) -> dict:
    _validate_tool_name(tool_name)
    registry = _get_registry()
    if not registry.has_tool(tool_name):
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
    obs, artifacts = registry.invoke(tool_name=tool_name, tool_input=tool_input)
    return {
        "status": obs.status,
        "summary": obs.summary,
        "payload": obs.payload,
        "artifacts": [
            {"pack_name": a.pack_name, "artifact_type": a.artifact_type, "title": a.title, "content": a.content, "uri": a.uri}
            for a in artifacts
        ],
    }
