"""Unit tests for the model registry service layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.model_registry.db import create_engine_for_url, create_session_factory, init_db
from services.model_registry.repository import ModelRegistryRepository
from services.model_registry.schemas import (
    ModelRegisterRequest,
    ModelStatus,
    ModelStatusUpdateRequest,
)
from services.model_registry.service import (
    ModelRegistryService,
    ModelValidationError,
)


@pytest.fixture
def model_registry_service(tmp_path: Path) -> ModelRegistryService:
    database_url = f"sqlite:///{tmp_path / 'model_registry_service.db'}"
    engine = create_engine_for_url(database_url)
    init_db(engine)
    session_factory = create_session_factory(engine)
    session = session_factory()
    try:
        yield ModelRegistryService(ModelRegistryRepository(session))
    finally:
        session.close()
        engine.dispose()


def test_register_model_and_lookup_latest_ready(
    model_registry_service: ModelRegistryService,
) -> None:
    model_registry_service.register_model(
        ModelRegisterRequest(
            region="henan",
            crop_type="wheat",
            task_type="baldness_detection",
            model_name="unet_rs_baldness",
            model_version="v1",
            artifact_uri="s3://models/henan/wheat/v1/model.pt",
            metrics_json={"miou": 0.81},
            status=ModelStatus.TRAINING,
        )
    )
    ready_model = model_registry_service.register_model(
        ModelRegisterRequest(
            region="henan",
            crop_type="wheat",
            task_type="baldness_detection",
            model_name="unet_rs_baldness",
            model_version="v2",
            artifact_uri="s3://models/henan/wheat/v2/model.pt",
            metrics_json={"miou": 0.86},
            status=ModelStatus.READY,
        )
    )

    lookup = model_registry_service.lookup_model(
        region="henan",
        crop_type="wheat",
        task_type="baldness_detection",
    )

    assert lookup.model_exists is True
    assert lookup.model_id == ready_model.id
    assert lookup.model_version == "v2"
    assert lookup.metrics_json == {"miou": 0.86}
    assert lookup.status == ModelStatus.READY


def test_lookup_returns_no_ready_model_reason(
    model_registry_service: ModelRegistryService,
) -> None:
    model_registry_service.register_model(
        ModelRegisterRequest(
            region="henan",
            crop_type="wheat",
            task_type="baldness_detection",
            model_name="unet_rs_baldness",
            model_version="v1",
            artifact_uri="s3://models/henan/wheat/v1/model.pt",
            status=ModelStatus.FAILED,
        )
    )

    lookup = model_registry_service.lookup_model(
        region="henan",
        crop_type="wheat",
        task_type="baldness_detection",
    )

    assert lookup.model_exists is False
    assert lookup.reason == (
        "no ready model found for region=henan crop_type=wheat task_type=baldness_detection"
    )


def test_status_update_and_invalid_transition(
    model_registry_service: ModelRegistryService,
) -> None:
    registered = model_registry_service.register_model(
        ModelRegisterRequest(
            region="jiangsu",
            crop_type="rice",
            task_type="yield_estimation",
            model_name="rice_yield_net",
            model_version="2026.03.15.1",
            artifact_uri="s3://models/jiangsu/rice/yield/model.pt",
            status=ModelStatus.TRAINING,
        )
    )

    ready_model = model_registry_service.set_model_status(
        registered.id,
        ModelStatusUpdateRequest(status=ModelStatus.READY),
    )
    assert ready_model.status == ModelStatus.READY

    deprecated_model = model_registry_service.set_model_status(
        registered.id,
        ModelStatusUpdateRequest(status=ModelStatus.DEPRECATED),
    )
    assert deprecated_model.status == ModelStatus.DEPRECATED

    with pytest.raises(ModelValidationError):
        model_registry_service.set_model_status(
            registered.id,
            ModelStatusUpdateRequest(status=ModelStatus.READY),
        )
