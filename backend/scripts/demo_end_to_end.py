"""Run a local end-to-end detect request against the API gateway app."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import httpx

from apps.api_gateway.main import create_app
from apps.orchestrator.config import get_orchestrator_runtime_config
from apps.orchestrator.service_registry import (
    get_model_registry_lookup_client,
    get_orchestrator_executor_agent,
    get_orchestrator_planner_agent,
    get_orchestrator_tool_executor,
)
from infra.llm.config import get_agent_llm_config
from infra.llm.provider import get_agent_llm_provider
from scripts.seed_demo_models import seed_demo_assets
from services.confidence_service.config import get_confidence_service_config
from services.inference_service.config import get_inference_service_config
from services.rag_service.config import get_rag_service_config
from services.report_service.config import get_report_service_config
from services.training_service.config import get_training_service_config
from services.visualization_service.config import get_visualization_service_config


def run_demo_request(
    base_dir: str | None = None,
    *,
    llm_provider_override: Any | None = None,
) -> dict[str, Any]:
    """Seed demo assets and run a detect request through the gateway app."""
    demo_root = Path(base_dir or "/tmp/ktp_demo_run")
    demo_root.mkdir(parents=True, exist_ok=True)
    os.environ["ORCHESTRATOR_DATABASE_URL"] = f"sqlite:///{demo_root / 'demo_registry.db'}"
    os.environ["VECTORSTORE_DIR"] = str(demo_root / "rag_store")
    os.environ["USE_MOCK_EMBEDDING"] = "true"
    os.environ["RAG_EMBEDDING_DIMENSION"] = "64"
    os.environ["REPORT_OUTPUT_DIR"] = str(demo_root / "reports")
    os.environ["MASK_OUTPUT_DIR"] = str(demo_root / "masks")
    os.environ["ORCHESTRATOR_INFERENCE_MASK_OUTPUT_DIR"] = str(demo_root / "masks")
    os.environ["VISUALIZATION_OUTPUT_DIR"] = str(demo_root / "visualizations")

    _clear_caches()
    seed_demo_assets(database_url=os.environ["ORCHESTRATOR_DATABASE_URL"])
    app = create_app(llm_provider_override=llm_provider_override)

    async def _run() -> dict[str, Any]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/detect",
                json={
                    "request_id": "req-demo-001",
                    "user_query": "Assess wheat health in Henan and provide a report with confidence.",
                    "region": "henan",
                    "crop_type": "wheat",
                    "task_type": "crop_health_detection",
                    "use_mock": True,
                    "extra_params": {},
                },
            )
            return response.json()

    return asyncio.run(_run())


def _clear_caches() -> None:
    try:
        from apps.orchestrator.graph.workflow import get_workflow
    except ModuleNotFoundError:
        get_workflow = None

    get_orchestrator_runtime_config.cache_clear()
    get_agent_llm_config.cache_clear()
    get_agent_llm_provider.cache_clear()
    get_model_registry_lookup_client.cache_clear()
    get_orchestrator_planner_agent.cache_clear()
    get_orchestrator_tool_executor.cache_clear()
    get_orchestrator_executor_agent.cache_clear()
    get_confidence_service_config.cache_clear()
    get_inference_service_config.cache_clear()
    get_rag_service_config.cache_clear()
    get_report_service_config.cache_clear()
    get_training_service_config.cache_clear()
    get_visualization_service_config.cache_clear()
    if get_workflow is not None:
        get_workflow.cache_clear()


if __name__ == "__main__":
    print(json.dumps(run_demo_request(), ensure_ascii=True, indent=2, sort_keys=True))
