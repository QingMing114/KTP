"""Probe the shared planner/executor Qwen runtime and report readiness."""

from __future__ import annotations

import json

from infra.llm.config import get_agent_llm_config
from infra.llm.provider import AgentLLMError, warm_up_agent_llm_provider


def main() -> int:
    """Print a structured runtime probe result for the shared Qwen worker."""
    config = get_agent_llm_config()
    result: dict[str, object] = {
        "backend": config.backend,
        "model_path": config.model_path,
        "runtime_python": config.runtime_python,
        "cuda_visible_devices": config.cuda_visible_devices,
        "require_accelerator": config.require_accelerator,
        "ready": False,
    }

    try:
        runtime = warm_up_agent_llm_provider()
    except AgentLLMError as exc:
        result["error"] = str(exc)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 1

    result["ready"] = True
    result["runtime"] = runtime or {}
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
