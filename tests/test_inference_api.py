"""API tests for the inference service."""

from __future__ import annotations

import asyncio
from concurrent.futures import TimeoutError as FutureTimeoutError
import os
from pathlib import Path
import threading

import httpx
import numpy as np
from PIL import Image
import pytest
import rasterio
from rasterio.transform import from_origin
from fastapi.testclient import TestClient

from services.inference_service.config import InferenceServiceConfig
from services.inference_service.loaders.model_loader import ModelLoader
from services.inference_service.main import create_app
from services.inference_service.predictors.mock_predictor import MockPredictor
from services.inference_service.predictors.real_predictor import RealPredictor
from services.inference_service.schemas import ResolvedModelMetadata
from services.inference_service.service import InferenceService


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _supports_testclient_runtime() -> bool:
    loop = asyncio.new_event_loop()
    ready = threading.Event()

    def run_loop() -> None:
        asyncio.set_event_loop(loop)
        ready.set()
        loop.run_forever()

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()
    ready.wait(timeout=1)
    try:
        future = asyncio.run_coroutine_threadsafe(asyncio.sleep(0, result=True), loop)
        return bool(future.result(timeout=0.5))
    except FutureTimeoutError:
        return False
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=1)


class ReadyModelRegistryClient:
    async def lookup_ready_model(
        self,
        *,
        region: str,
        crop_type: str,
        task_type: str,
    ) -> ResolvedModelMetadata | None:
        return ResolvedModelMetadata(
            model_id=7,
            model_name=f"{crop_type}-{task_type}-rf",
            model_version="v5",
            artifact_uri=f"mock://models/{region}/{crop_type}/{task_type}/v5/model.pkl",
            status="ready",
        )


class EmptyModelRegistryClient:
    async def lookup_ready_model(
        self,
        *,
        region: str,
        crop_type: str,
        task_type: str,
        ) -> ResolvedModelMetadata | None:
        return None


EXTERNAL_RF_MODEL_PATH = Path(
    os.environ.get("KTP_TEST_RF_MODEL_PATH", "var/models/baldness/rf_model.pkl")
)


class ReadyRealModelRegistryClient:
    async def lookup_ready_model(
        self,
        *,
        region: str,
        crop_type: str,
        task_type: str,
    ) -> ResolvedModelMetadata | None:
        return ResolvedModelMetadata(
            model_id=8,
            model_name=f"{crop_type}-{task_type}-rf",
            model_version="external-rf",
            artifact_uri=str(EXTERNAL_RF_MODEL_PATH),
            status="ready",
            metrics_json={
                "prediction_class_semantics": {
                    "class_labels": {
                        "1": "baldness",
                        "2": "water",
                        "3": "non_crop_vegetation",
                        "4": "sorghum",
                    },
                    "target_classes": [1],
                }
            },
        )


class ReadyRealModelRegistryClientWithoutSemantics:
    async def lookup_ready_model(
        self,
        *,
        region: str,
        crop_type: str,
        task_type: str,
    ) -> ResolvedModelMetadata | None:
        return ResolvedModelMetadata(
            model_id=9,
            model_name=f"{crop_type}-{task_type}-rf",
            model_version="external-rf",
            artifact_uri=str(EXTERNAL_RF_MODEL_PATH),
            status="ready",
        )


def _write_demo_image(tmp_path: Path) -> Path:
    image_path = tmp_path / "demo.png"
    image_array = np.zeros((16, 16, 3), dtype=np.uint8)
    image_array[4:12, 5:13] = 255
    Image.fromarray(image_array).save(image_path)
    return image_path


def _write_multiband_demo_tiff(tmp_path: Path) -> Path:
    image_path = tmp_path / "demo_multiband.tif"
    bands = np.zeros((6, 24, 24), dtype=np.float32)
    for band_index in range(6):
        bands[band_index] = 20.0 + band_index * 5.0

    bands[0, 8:18, 8:18] = 35.0
    bands[1, 8:18, 8:18] = 50.0
    bands[2, 8:18, 8:18] = 65.0
    bands[3, 8:18, 8:18] = 80.0
    bands[4, 8:18, 8:18] = 95.0
    bands[5, 8:18, 8:18] = 140.0

    with rasterio.open(
        image_path,
        "w",
        driver="GTiff",
        height=bands.shape[1],
        width=bands.shape[2],
        count=bands.shape[0],
        dtype="float32",
        transform=from_origin(100, 100, 1, 1),
    ) as dst:
        dst.write(bands)
    return image_path


def _create_test_app(tmp_path: Path, model_registry_client: object):
    config = InferenceServiceConfig(
        inference_service_name="inference-service",
        model_registry_url="http://unused.local",
        default_task_type="baldness_detection",
        default_use_mock=True,
        mask_output_dir=str(tmp_path / "masks"),
        real_predictor_backend="baldness_rf",
        baldness_rf_source_root=os.environ.get("KTP_TEST_BALDNESS_SOURCE_ROOT", "."),
        baldness_rf_default_model_path=str(EXTERNAL_RF_MODEL_PATH),
        baldness_rf_work_dir=str(tmp_path / "rf_work"),
        inference_http_timeout_seconds=1.0,
    )
    service = InferenceService(
        config=config,
        model_registry_client=model_registry_client,
        model_loader=ModelLoader(config=config),
        mock_predictor=MockPredictor(),
        real_predictor=RealPredictor(config=config),
    )
    return create_app(config=config, service=service)


@pytest.mark.anyio
async def test_inference_api_health_and_success_path(tmp_path: Path) -> None:
    image_path = _write_demo_image(tmp_path)
    app = _create_test_app(tmp_path, ReadyModelRegistryClient())

    if _supports_testclient_runtime():
        with TestClient(app) as client:
            _assert_health_and_success(client, image_path)
    else:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await _assert_health_and_success_async(client, image_path)


@pytest.mark.anyio
async def test_inference_api_returns_structured_failure_when_no_model_exists(
    tmp_path: Path,
) -> None:
    image_path = _write_demo_image(tmp_path)
    app = _create_test_app(tmp_path, EmptyModelRegistryClient())

    if _supports_testclient_runtime():
        with TestClient(app) as client:
            response = client.post(
                "/infer",
                json={
                    "request_id": "req-infer-no-model",
                    "region": "henan",
                    "crop_type": "wheat",
                    "task_type": "baldness_detection",
                    "image_path": str(image_path),
                    "use_mock": True,
                    "extra_params": {},
                },
            )
    else:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/infer",
                json={
                    "request_id": "req-infer-no-model",
                    "region": "henan",
                    "crop_type": "wheat",
                    "task_type": "baldness_detection",
                    "image_path": str(image_path),
                    "use_mock": True,
                    "extra_params": {},
                },
            )

    assert response.status_code == 200
    payload = response.json()
    assert payload["request_id"] == "req-infer-no-model"
    assert payload["success"] is False
    assert payload["result"] is None
    assert "no ready model found" in payload["message"]


@pytest.mark.anyio
async def test_inference_api_real_baldness_rf_path(tmp_path: Path) -> None:
    if not EXTERNAL_RF_MODEL_PATH.exists():
        pytest.skip("external RF model is not available in this environment")

    image_path = _write_multiband_demo_tiff(tmp_path)
    app = _create_test_app(tmp_path, ReadyRealModelRegistryClient())

    if _supports_testclient_runtime():
        with TestClient(app) as client:
            response = client.post(
                "/infer",
                json={
                    "request_id": "req-infer-real-rf",
                    "region": "henan",
                    "crop_type": "wheat",
                    "task_type": "baldness_detection",
                    "image_path": str(image_path),
                    "use_mock": False,
                    "extra_params": {},
                },
            )
    else:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/infer",
                json={
                    "request_id": "req-infer-real-rf",
                    "region": "henan",
                    "crop_type": "wheat",
                    "task_type": "baldness_detection",
                    "image_path": str(image_path),
                    "use_mock": False,
                    "extra_params": {},
                },
            )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["result"]["model_version"] == "external-rf"
    assert Path(payload["result"]["mask_uri"]).exists()
    assert payload["result"]["mask_uri"].endswith("_target_mask.tif")
    assert payload["result"]["raw_prediction_uri"].endswith("class.tif")
    assert payload["result"]["target_classes"] == [1]
    assert payload["result"]["confidence"] >= 0.0


@pytest.mark.anyio
async def test_inference_api_real_multiclass_path_fails_without_semantics(
    tmp_path: Path,
) -> None:
    if not EXTERNAL_RF_MODEL_PATH.exists():
        pytest.skip("external RF model is not available in this environment")

    image_path = _write_multiband_demo_tiff(tmp_path)
    app = _create_test_app(tmp_path, ReadyRealModelRegistryClientWithoutSemantics())

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/infer",
            json={
                "request_id": "req-infer-real-rf-no-semantics",
                "region": "henan",
                "crop_type": "wheat",
                "task_type": "baldness_detection",
                "image_path": str(image_path),
                "use_mock": False,
                "extra_params": {},
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert "prediction_class_semantics" in payload["message"]


def _assert_health_and_success(client: TestClient, image_path: Path) -> None:
    health_response = client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json()["service"] == "inference-service"

    infer_response = client.post(
        "/infer",
        json={
            "request_id": "req-infer-success",
            "region": "henan",
            "crop_type": "wheat",
            "task_type": "baldness_detection",
            "image_path": str(image_path),
            "use_mock": True,
            "extra_params": {},
        },
    )
    assert infer_response.status_code == 200
    payload = infer_response.json()
    assert payload["success"] is True
    assert payload["message"] == "inference completed"
    assert payload["result"]["model_version"] == "v5"
    assert Path(payload["result"]["mask_uri"]).exists()
    assert payload["result"]["affected_area"] > 0


async def _assert_health_and_success_async(
    client: httpx.AsyncClient,
    image_path: Path,
) -> None:
    health_response = await client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json()["service"] == "inference-service"

    infer_response = await client.post(
        "/infer",
        json={
            "request_id": "req-infer-success",
            "region": "henan",
            "crop_type": "wheat",
            "task_type": "baldness_detection",
            "image_path": str(image_path),
            "use_mock": True,
            "extra_params": {},
        },
    )
    assert infer_response.status_code == 200
    payload = infer_response.json()
    assert payload["success"] is True
    assert payload["message"] == "inference completed"
    assert payload["result"]["model_version"] == "v5"
    assert Path(payload["result"]["mask_uri"]).exists()
    assert payload["result"]["affected_area"] > 0
