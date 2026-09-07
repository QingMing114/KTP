"""Run the real baldness-detection flow with RF inference, report, and confidence."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEMO_DIR = BACKEND_ROOT / "var" / "runtime" / "baldness_real_flow"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import httpx
import rasterio
from rasterio.windows import Window

from apps.api_gateway.main import create_app
from scripts.start_gateway_qwen_local import clear_runtime_caches
from services.model_registry.db import create_engine_for_url, create_session_factory, init_db
from services.model_registry.repository import ModelRegistryRepository
from services.model_registry.schemas import ModelRegisterRequest, ModelStatus
from services.model_registry.service import ModelRegistryService
from services.rag_service.config import get_rag_service_config
from services.rag_service.schemas import DocumentIngestRequest
from services.rag_service.service import RAGService


BALDNESS_RAG_TEXT = (
    "Baldness detection results should be interpreted together with the predicted lesion area, "
    "confidence map, and the spatial continuity of the positive region. A higher affected area and "
    "stable confidence map usually indicate stronger evidence for visible baldness-related regions."
)

BALDNESS_RF_CLASS_SEMANTICS = {
    "class_labels": {
        "1": "baldness",
        "2": "water",
        "3": "non_crop_vegetation",
        "4": "sorghum",
    },
    "target_classes": [1],
    "background_classes": [0],
    "source": "bantushibie_results_dir_name",
}


def build_runtime_paths(base_dir: str) -> dict[str, str]:
    """Build the runtime directory layout for the real baldness demo."""
    root = Path(base_dir).expanduser().resolve()
    return {
        "root": str(root),
        "database_path": str(root / "registry.db"),
        "vectorstore_dir": str(root / "rag_store"),
        "report_output_dir": str(root / "reports"),
        "mask_output_dir": str(root / "masks"),
        "visualization_output_dir": str(root / "visualizations"),
        "rf_work_dir": str(root / "rf_outputs"),
        "input_dir": str(root / "inputs"),
        "response_path": str(root / "response.json"),
    }


def configure_baldness_demo_environment(
    *,
    base_dir: str,
    agent_backend: str,
    model_dir: str,
    runtime_python: str,
    cuda_visible_devices: str,
) -> dict[str, str]:
    """Configure environment variables for the real baldness demo runtime."""
    paths = build_runtime_paths(base_dir)
    Path(paths["root"]).mkdir(parents=True, exist_ok=True)
    Path(paths["input_dir"]).mkdir(parents=True, exist_ok=True)
    os.environ["ORCHESTRATOR_DATABASE_URL"] = f"sqlite:///{paths['database_path']}"
    os.environ["VECTORSTORE_DIR"] = paths["vectorstore_dir"]
    os.environ["USE_MOCK_EMBEDDING"] = "true"
    os.environ["RAG_EMBEDDING_DIMENSION"] = "64"
    os.environ["REPORT_OUTPUT_DIR"] = paths["report_output_dir"]
    os.environ["MASK_OUTPUT_DIR"] = paths["mask_output_dir"]
    os.environ["ORCHESTRATOR_INFERENCE_MASK_OUTPUT_DIR"] = paths["mask_output_dir"]
    os.environ["VISUALIZATION_OUTPUT_DIR"] = paths["visualization_output_dir"]
    os.environ["BALDNESS_RF_WORK_DIR"] = paths["rf_work_dir"]
    os.environ["AGENT_LLM_BACKEND"] = agent_backend
    if agent_backend == "subprocess_qwen":
        os.environ["AGENT_LLM_MODEL_PATH"] = model_dir
        os.environ["AGENT_LLM_RUNTIME_PYTHON"] = runtime_python
        os.environ["AGENT_LLM_CUDA_VISIBLE_DEVICES"] = cuda_visible_devices
    return paths


def crop_multiband_image(
    *,
    source_image_path: str,
    output_image_path: str,
    crop_size: int,
) -> str:
    """Crop the center window from a multiband raster for repeatable local demos."""
    source_path = Path(source_image_path)
    output_path = Path(output_image_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(source_path) as src:
        width = min(crop_size, src.width)
        height = min(crop_size, src.height)
        col_off = max((src.width - width) // 2, 0)
        row_off = max((src.height - height) // 2, 0)
        window = Window(col_off=col_off, row_off=row_off, width=width, height=height)
        profile = src.profile.copy()
        profile.update(
            width=width,
            height=height,
            transform=src.window_transform(window),
        )
        data = src.read(window=window)
        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(data)
    return str(output_path)


def seed_baldness_real_assets(
    *,
    database_url: str,
    artifact_uri: str,
    document_text: str = BALDNESS_RAG_TEXT,
) -> None:
    """Seed the model registry and RAG store for the real baldness workflow."""
    engine = create_engine_for_url(database_url)
    init_db(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        service = ModelRegistryService(ModelRegistryRepository(session))
        try:
            service.register_model(
                ModelRegisterRequest(
                    region="scalp",
                    crop_type="hair",
                    task_type="baldness_detection",
                    model_name="baldness-rf",
                    model_version="rf-real-001",
                    artifact_uri=artifact_uri,
                    metrics_json={
                        "source": "bantushibie",
                        "kind": "real_rf",
                        "prediction_class_semantics": BALDNESS_RF_CLASS_SEMANTICS,
                    },
                    status=ModelStatus.READY,
                )
            )
        except Exception:
            pass
    engine.dispose()

    rag_service = RAGService(config=get_rag_service_config())
    try:
        rag_service.ingest_document(
            DocumentIngestRequest(
                document_id="doc-baldness-real-flow-001",
                title="Baldness Detection Interpretation Guide",
                source="local://knowledge/baldness/interpretation",
                text=document_text,
                metadata={
                    "region": "scalp",
                    "crop_type": "hair",
                    "task_type": "baldness_detection",
                },
            )
        )
    except Exception:
        pass


async def _post_detect(payload: dict[str, Any]) -> dict[str, Any]:
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.post("/detect", json=payload)
        return {
            "status_code": response.status_code,
            "payload": response.json(),
        }


def run_baldness_real_demo(
    *,
    base_dir: str | None = None,
    source_image_path: str | None = None,
    model_path: str | None = None,
    request_id: str = "req-baldness-real-001",
    crop_size: int = 512,
    agent_backend: str = "subprocess_qwen",
    model_dir: str = "",
    runtime_python: str = sys.executable,
    cuda_visible_devices: str = "auto:2",
) -> dict[str, Any]:
    """Run the full real baldness flow through the gateway app."""
    if not source_image_path or not model_path:
        raise ValueError("source_image_path and model_path must be provided")
    paths = configure_baldness_demo_environment(
        base_dir=base_dir or str(DEFAULT_DEMO_DIR),
        agent_backend=agent_backend,
        model_dir=model_dir,
        runtime_python=runtime_python,
        cuda_visible_devices=cuda_visible_devices,
    )
    clear_runtime_caches()
    crop_image_path = crop_multiband_image(
        source_image_path=source_image_path,
        output_image_path=str(Path(paths["input_dir"]) / f"{request_id}_crop.tif"),
        crop_size=crop_size,
    )
    seed_baldness_real_assets(
        database_url=os.environ["ORCHESTRATOR_DATABASE_URL"],
        artifact_uri=model_path,
    )
    response = asyncio.run(
        _post_detect(
            {
                "request_id": request_id,
                "user_query": (
                    "请对这张头皮多光谱影像做真实斑秃识别，并生成分析报告、解释结果和置信度说明。"
                ),
                "region": "scalp",
                "crop_type": "hair",
                "task_type": "baldness_detection",
                "image_path": crop_image_path,
                "use_mock": False,
                "extra_params": {},
            }
        )
    )
    payload = response["payload"]
    output = {
        "status_code": response["status_code"],
        "request_id": payload.get("request_id"),
        "success": payload.get("success"),
        "workflow_status": payload.get("workflow_status"),
        "cropped_image_path": crop_image_path,
        "inference_result": payload.get("inference_result"),
        "rag_result": payload.get("rag_result"),
        "report_result": payload.get("report_result"),
        "confidence_result": payload.get("confidence_result"),
        "visualization_result": payload.get("visualization_result"),
        "message": payload.get("message"),
    }
    Path(paths["response_path"]).write_text(
        json.dumps(output, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    return output


def parse_args() -> argparse.Namespace:
    """Parse command-line options for the real baldness demo script."""
    parser = argparse.ArgumentParser(
        description="Run the real baldness-detection flow with report and confidence output."
    )
    parser.add_argument(
        "--base-dir",
        default=str(DEFAULT_DEMO_DIR),
        help="Runtime output directory for SQLite, cropped inputs, RF outputs, and reports.",
    )
    parser.add_argument(
        "--source-image-path",
        required=True,
        help="Real multispectral source image.",
    )
    parser.add_argument(
        "--model-path",
        required=True,
        help="Real RF model artifact path.",
    )
    parser.add_argument(
        "--request-id",
        default="req-baldness-real-001",
        help="Request identifier for the workflow run.",
    )
    parser.add_argument(
        "--crop-size",
        type=int,
        default=512,
        help="Center crop size used to keep the real demo runnable.",
    )
    parser.add_argument(
        "--agent-backend",
        choices=["subprocess_qwen", "heuristic"],
        default="subprocess_qwen",
        help="Planner/executor backend used during the demo.",
    )
    parser.add_argument(
        "--model-dir",
        default="",
        help="Shared Qwen model directory for planner/executor when enabled.",
    )
    parser.add_argument(
        "--runtime-python",
        default=sys.executable,
        help="Python executable used by the external Qwen worker.",
    )
    parser.add_argument(
        "--cuda-visible-devices",
        default="auto:2",
        help="Comma-separated GPU ids or `auto:<count>` exposed to the shared Qwen worker.",
    )
    return parser.parse_args()


def main() -> int:
    """CLI entrypoint for the real baldness flow demo."""
    args = parse_args()
    result = run_baldness_real_demo(
        base_dir=args.base_dir,
        source_image_path=args.source_image_path,
        model_path=args.model_path,
        request_id=args.request_id,
        crop_size=args.crop_size,
        agent_backend=args.agent_backend,
        model_dir=args.model_dir,
        runtime_python=args.runtime_python,
        cuda_visible_devices=args.cuda_visible_devices,
    )
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
