"""Start the API gateway with a local SQLite demo runtime and shared Qwen worker."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def build_runtime_paths(base_dir: str) -> dict[str, str]:
    """Build local runtime paths for the gateway demo environment."""
    root = Path(base_dir).expanduser().resolve()
    return {
        "root": str(root),
        "database_path": str(root / "registry.db"),
        "vectorstore_dir": str(root / "rag_store"),
        "report_output_dir": str(root / "reports"),
        "mask_output_dir": str(root / "masks"),
        "visualization_output_dir": str(root / "visualizations"),
    }


def configure_demo_environment(
    *,
    base_dir: str,
    port: int,
    model_path: str,
    runtime_python: str,
    cuda_visible_devices: str,
) -> dict[str, str]:
    """Apply environment variables for a local Qwen-backed gateway runtime."""
    paths = build_runtime_paths(base_dir)
    Path(paths["root"]).mkdir(parents=True, exist_ok=True)
    os.environ["APP_PORT"] = str(port)
    os.environ["DATABASE_URL"] = f"sqlite:///{paths['database_path']}"
    os.environ["ORCHESTRATOR_DATABASE_URL"] = f"sqlite:///{paths['database_path']}"
    os.environ["VECTORSTORE_DIR"] = paths["vectorstore_dir"]
    os.environ["USE_MOCK_EMBEDDING"] = "true"
    os.environ["RAG_EMBEDDING_DIMENSION"] = "64"
    os.environ["REPORT_OUTPUT_DIR"] = paths["report_output_dir"]
    os.environ["MASK_OUTPUT_DIR"] = paths["mask_output_dir"]
    os.environ["ORCHESTRATOR_INFERENCE_MASK_OUTPUT_DIR"] = paths["mask_output_dir"]
    os.environ["VISUALIZATION_OUTPUT_DIR"] = paths["visualization_output_dir"]
    os.environ["AGENT_LLM_BACKEND"] = "subprocess_qwen"
    os.environ["AGENT_LLM_MODEL_PATH"] = model_path
    os.environ["AGENT_LLM_RUNTIME_PYTHON"] = runtime_python
    os.environ["AGENT_LLM_CUDA_VISIBLE_DEVICES"] = cuda_visible_devices
    return paths


def clear_runtime_caches() -> None:
    """Clear cached config and runtime singletons before starting the gateway."""
    from apps.orchestrator.config import get_orchestrator_runtime_config
    from apps.orchestrator.graph.workflow import get_workflow
    from apps.orchestrator.service_registry import (
        get_model_registry_lookup_client,
        get_orchestrator_executor_agent,
        get_orchestrator_planner_agent,
        get_orchestrator_tool_executor,
    )
    from infra.llm.config import get_agent_llm_config
    from infra.llm.provider import get_agent_llm_provider
    from services.confidence_service.config import get_confidence_service_config
    from services.inference_service.config import get_inference_service_config
    from services.rag_service.config import get_rag_service_config
    from services.report_service.config import get_report_service_config
    from services.training_service.config import get_training_service_config
    from services.visualization_service.config import get_visualization_service_config

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
    get_workflow.cache_clear()


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the local gateway starter."""
    parser = argparse.ArgumentParser(
        description="Start the local API gateway with SQLite demo storage and Qwen agents."
    )
    parser.add_argument("--host", default="0.0.0.0", help="Gateway bind host.")
    parser.add_argument("--port", type=int, default=18080, help="Gateway bind port.")
    parser.add_argument(
        "--base-dir",
        default="/tmp/ktp_qwen_gateway",
        help="Local runtime directory for SQLite, reports, masks, and RAG files.",
    )
    parser.add_argument(
        "--model-path",
        default="/home/D/liumeng/models/Qwen3-VL-30B-A3B-Instruct",
        help="Local Qwen model directory.",
    )
    parser.add_argument(
        "--runtime-python",
        default="/opt/anaconda3/bin/python",
        help="Python executable used by the external Qwen worker.",
    )
    parser.add_argument(
        "--cuda-visible-devices",
        default="auto:2",
        help="Comma-separated GPU ids or `auto:<count>` exposed to the shared Qwen worker.",
    )
    parser.add_argument(
        "--artifact-uri",
        default="mock://models/wheat-health-segmentation/demo-v1",
        help="Artifact URI used for the seeded demo model.",
    )
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Do not seed the local registry and knowledge store before startup.",
    )
    return parser.parse_args()


def main() -> int:
    """Start the local gateway after preparing runtime environment and demo data."""
    args = parse_args()
    configure_demo_environment(
        base_dir=args.base_dir,
        port=args.port,
        model_path=args.model_path,
        runtime_python=args.runtime_python,
        cuda_visible_devices=args.cuda_visible_devices,
    )
    clear_runtime_caches()

    if not args.no_seed:
        from scripts.seed_demo_models import seed_demo_assets

        seed_demo_assets(
            database_url=os.environ["ORCHESTRATOR_DATABASE_URL"],
            artifact_uri=args.artifact_uri,
        )

    import uvicorn

    uvicorn.run(
        "apps.api_gateway.main:app",
        host=args.host,
        port=args.port,
        log_level="info",
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
