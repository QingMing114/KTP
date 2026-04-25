from __future__ import annotations

import ipaddress
import json
import logging
import subprocess
from typing import Any, Callable
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

from v2.shared.schemas import ObservationV2, PackArtifactView

logger = logging.getLogger(__name__)

_ALLOWED_COMMANDS: set[str] = {"python3", "python", "node", "Rscript", "java", "bash", "sh"}
_ALLOWED_MODULE_PREFIXES: list[str] = [
    "v2.",
    "services.",
    "shared.",
    "apps.",
    "prosail_",
    "ml.",
]
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


class ToolEndpoint(BaseModel):
    adapter: str = Field(description="python_callable | subprocess | http_api")
    module: str | None = Field(default=None, description="Python module path for python_callable adapter")
    function: str | None = Field(default=None, description="Python function name for python_callable adapter")
    command: list[str] | None = Field(default=None, description="Command for subprocess adapter")
    url: str | None = Field(default=None, description="URL for http_api adapter")
    method: str = Field(default="POST", description="HTTP method for http_api adapter")
    headers: dict[str, str] = Field(default_factory=dict, description="HTTP headers for http_api adapter")
    timeout: float = Field(default=30.0, description="Timeout in seconds (max 120)")
    env: dict[str, str] | None = Field(default=None, description="Extra env vars for subprocess adapter")
    cwd: str | None = Field(default=None, description="Working directory for subprocess adapter")

    def model_post_init(self, __context: Any) -> None:
        if self.timeout > 120:
            self.timeout = 120.0


class ToolOutputMapping(BaseModel):
    status_path: str = Field(default="status", description="JSON path to status field in output")
    summary_path: str = Field(default="summary", description="JSON path to summary field in output")
    payload_path: str | None = Field(default="payload", description="JSON path to payload dict in output")
    artifacts_path: str | None = Field(default="artifacts", description="JSON path to artifacts list in output")


class PluginToolSpec(BaseModel):
    name: str = Field(description="Unique tool name, e.g. mypack.my_tool")
    display_name: str = Field(default="", description="Human-readable name")
    description: str = Field(description="What this tool does")
    category: str = Field(default="plugin", description="Tool category")
    pack_name: str = Field(default="plugin", description="Pack name")
    usage_hint: str | None = Field(default=None, description="When to use this tool")
    input_schema: dict[str, str] = Field(default_factory=dict, description="Input param name -> type hint")
    safety_level: str = Field(default="safe", description="safe | caution | dangerous")
    endpoint: ToolEndpoint = Field(description="How to invoke this tool")
    output_mapping: ToolOutputMapping = Field(default_factory=ToolOutputMapping, description="How to parse output")
    enabled: bool = Field(default=True)


def _resolve_json_path(data: dict, path: str, default: Any = None) -> Any:
    parts = path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return default
    return current


def _is_private_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return True
        try:
            ip = ipaddress.ip_address(hostname)
            return any(ip in net for net in _PRIVATE_NETWORKS)
        except ValueError:
            return hostname in ("localhost", "localhost.localdomain")
    except Exception:
        return True


def _invoke_python_callable(endpoint: ToolEndpoint, tool_input: dict) -> dict:
    if not endpoint.module or not endpoint.function:
        raise ValueError("python_callable adapter requires 'module' and 'function'")
    allowed = any(endpoint.module.startswith(prefix) for prefix in _ALLOWED_MODULE_PREFIXES)
    if not allowed:
        raise ValueError(
            f"Module '{endpoint.module}' not in allowed prefixes: {_ALLOWED_MODULE_PREFIXES}. "
            "Add the prefix to _ALLOWED_MODULE_PREFIXES to enable it."
        )
    import importlib
    mod = importlib.import_module(endpoint.module)
    fn = getattr(mod, endpoint.function)
    if not callable(fn):
        raise ValueError(f"{endpoint.module}.{endpoint.function} is not callable")
    result = fn(**tool_input)
    if isinstance(result, tuple) and len(result) == 2:
        obs, artifacts = result
        if isinstance(obs, ObservationV2):
            output = {
                "status": obs.status,
                "summary": obs.summary,
                "payload": obs.payload,
            }
            if artifacts and isinstance(artifacts, list):
                output["artifacts"] = [
                    {"pack_name": a.pack_name, "artifact_type": a.artifact_type, "title": a.title, "content": a.content, "uri": a.uri}
                    for a in artifacts if isinstance(a, PackArtifactView)
                ]
            return output
    if isinstance(result, dict):
        return result
    if isinstance(result, ObservationV2):
        return {"status": result.status, "summary": result.summary, "payload": result.payload}
    return {"status": "success", "summary": str(result)}


def _invoke_subprocess(endpoint: ToolEndpoint, tool_input: dict) -> dict:
    if not endpoint.command:
        raise ValueError("subprocess adapter requires 'command'")
    base_cmd = endpoint.command[0]
    from pathlib import Path
    cmd_name = Path(base_cmd).name
    if cmd_name not in _ALLOWED_COMMANDS:
        raise ValueError(
            f"Command '{cmd_name}' not in allowed set: {_ALLOWED_COMMANDS}. "
            "Add the command to _ALLOWED_COMMANDS to enable it."
        )
    import os
    env = os.environ.copy()
    if endpoint.env:
        env.update(endpoint.env)
    input_json = json.dumps(tool_input)
    cwd = endpoint.cwd or None
    result = subprocess.run(
        endpoint.command,
        input=input_json,
        capture_output=True,
        text=True,
        timeout=endpoint.timeout,
        env=env,
        cwd=cwd,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()[:2000]
        return {"status": "error", "summary": f"Process exited with code {result.returncode}: {stderr}"}
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"status": "success", "summary": result.stdout.strip()[:2000]}
    return output


def _invoke_http_api(endpoint: ToolEndpoint, tool_input: dict) -> dict:
    if not endpoint.url:
        raise ValueError("http_api adapter requires 'url'")
    if _is_private_url(endpoint.url):
        raise ValueError(
            f"URL '{endpoint.url}' points to a private/internal network address. "
            "External URLs only for security."
        )
    with httpx.Client(timeout=endpoint.timeout) as client:
        if endpoint.method.upper() == "GET":
            resp = client.request(endpoint.method, endpoint.url, params=tool_input, headers=endpoint.headers)
        else:
            resp = client.request(endpoint.method, endpoint.url, json=tool_input, headers=endpoint.headers)
    if resp.status_code >= 400:
        return {"status": "error", "summary": f"HTTP {resp.status_code}: {resp.text[:2000]}"}
    try:
        output = resp.json()
    except json.JSONDecodeError:
        return {"status": "success", "summary": resp.text[:2000]}
    return output


_ADAPTERS = {
    "python_callable": _invoke_python_callable,
    "subprocess": _invoke_subprocess,
    "http_api": _invoke_http_api,
}


def invoke_plugin_tool(spec: PluginToolSpec, tool_input: dict) -> tuple[ObservationV2, list[PackArtifactView]]:
    adapter_fn = _ADAPTERS.get(spec.endpoint.adapter)
    if adapter_fn is None:
        return (
            ObservationV2(source=spec.name, status="error", summary=f"Unknown adapter: {spec.endpoint.adapter}"),
            [],
        )
    try:
        raw_output = adapter_fn(spec.endpoint, tool_input)
    except subprocess.TimeoutExpired:
        return (
            ObservationV2(source=spec.name, status="error", summary=f"Tool timed out after {spec.endpoint.timeout}s"),
            [],
        )
    except ValueError as exc:
        return (
            ObservationV2(source=spec.name, status="error", summary=str(exc)),
            [],
        )
    except Exception as exc:
        logger.exception("Plugin tool %s failed", spec.name)
        return (
            ObservationV2(source=spec.name, status="error", summary=f"Tool invocation failed: {exc}"),
            [],
        )

    if not isinstance(raw_output, dict):
        raw_output = {"status": "success", "summary": str(raw_output)}

    mapping = spec.output_mapping
    status = _resolve_json_path(raw_output, mapping.status_path, "success")
    summary = _resolve_json_path(raw_output, mapping.summary_path, "Tool completed")
    payload = _resolve_json_path(raw_output, mapping.payload_path, {})
    if not isinstance(payload, dict):
        payload = {"value": payload}

    artifacts = []
    raw_artifacts = _resolve_json_path(raw_output, mapping.artifacts_path)
    if isinstance(raw_artifacts, list):
        for item in raw_artifacts:
            if isinstance(item, dict):
                artifacts.append(PackArtifactView(
                    pack_name=item.get("pack_name", spec.pack_name),
                    artifact_type=item.get("artifact_type", "generic"),
                    title=item.get("title", "Artifact"),
                    content=item.get("content"),
                    uri=item.get("uri"),
                ))
            elif isinstance(item, PackArtifactView):
                artifacts.append(item)

    return (
        ObservationV2(source=spec.name, status=status, summary=summary, payload=payload),
        artifacts,
    )


def make_plugin_handler(spec: PluginToolSpec) -> Callable:
    def handler(**kwargs) -> tuple[ObservationV2, list[PackArtifactView]]:
        return invoke_plugin_tool(spec, kwargs)
    handler.__name__ = f"plugin_{spec.name.replace('.', '_')}"
    handler.__doc__ = spec.description
    return handler
