"""Start a demo training workflow request."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.training_service.client import start_training_workflow
from services.training_service.schemas import TrainingRequest


async def run_demo() -> None:
    request = TrainingRequest(
        request_id="demo-training-001",
        region="henan",
        crop_type="wheat",
        task_type="baldness_detection",
        dataset_uri="mock://datasets/henan/wheat/raw",
        base_model_name="unet_rs_baldness_base",
        output_model_name="unet_rs_baldness",
        output_model_version="v4",
        trigger_reason="model_missing",
    )
    result = await start_training_workflow(request)
    print(json.dumps(result.model_dump(), ensure_ascii=True, indent=2))


def main() -> None:
    asyncio.run(run_demo())


if __name__ == "__main__":
    main()
