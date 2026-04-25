"""Business logic for the model registry service."""

from __future__ import annotations

import logging

from sqlalchemy.exc import IntegrityError

from services.model_registry.repository import ModelRegistryRepository
from services.model_registry.schemas import (
    ModelListResponse,
    ModelLookupResponse,
    ModelRegisterRequest,
    ModelResponse,
    ModelStatus,
    ModelStatusUpdateRequest,
)

logger = logging.getLogger(__name__)


class ModelRegistryError(Exception):
    """Base error for model registry operations."""

    error_code = "model_registry_error"
    status_code = 400

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class ModelNotFoundError(ModelRegistryError):
    """Raised when a target model cannot be found."""

    error_code = "model_not_found"
    status_code = 404


class ModelValidationError(ModelRegistryError):
    """Raised when model registry inputs or transitions are invalid."""

    error_code = "model_validation_error"
    status_code = 400


class ModelRegistryService:
    """Business operations exposed by the model registry service."""

    _allowed_transitions: dict[ModelStatus, set[ModelStatus]] = {
        ModelStatus.TRAINING: {
            ModelStatus.READY,
            ModelStatus.FAILED,
            ModelStatus.DEPRECATED,
        },
        ModelStatus.READY: {ModelStatus.DEPRECATED},
        ModelStatus.FAILED: {ModelStatus.TRAINING, ModelStatus.DEPRECATED},
        ModelStatus.DEPRECATED: set(),
    }

    def __init__(self, repository: ModelRegistryRepository) -> None:
        self._repository = repository

    def register_model(self, request: ModelRegisterRequest) -> ModelResponse:
        """Validate and persist a newly registered model."""
        logger.info(
            "model_registration_started | region=%s | crop_type=%s | task_type=%s | version=%s",
            request.region,
            request.crop_type,
            request.task_type,
            request.model_version,
        )
        try:
            model = self._repository.create_model(
                region=request.region,
                crop_type=request.crop_type,
                task_type=request.task_type,
                model_name=request.model_name,
                model_version=request.model_version,
                artifact_uri=request.artifact_uri,
                metrics_json=request.metrics_json,
                status=request.status,
                description=request.description,
            )
            self._repository.commit()
        except IntegrityError as exc:
            self._repository.rollback()
            logger.warning("model_registration_failed | reason=duplicate_identity")
            raise ModelValidationError(
                "A model with the same region, crop_type, task_type, model_name, and model_version already exists."
            ) from exc

        logger.info("model_registration_succeeded | model_id=%s", model.id)
        return ModelResponse.model_validate(model)

    def get_model_by_id(self, model_id: int) -> ModelResponse:
        """Return a model by identifier or raise a structured error."""
        logger.info("model_get_by_id_started | model_id=%s", model_id)
        model = self._repository.get_model_by_id(model_id)
        if model is None:
            logger.warning("model_get_by_id_failed | model_id=%s", model_id)
            raise ModelNotFoundError(f"Model with id={model_id} was not found.")
        logger.info("model_get_by_id_succeeded | model_id=%s", model_id)
        return ModelResponse.model_validate(model)

    def lookup_model(
        self,
        *,
        region: str,
        crop_type: str,
        task_type: str,
    ) -> ModelLookupResponse:
        """Return the latest ready model for a region/crop/task combination."""
        logger.info(
            "model_lookup_started | region=%s | crop_type=%s | task_type=%s",
            region,
            crop_type,
            task_type,
        )
        model = self._repository.get_latest_ready_model(region, crop_type, task_type)
        if model is None:
            reason = (
                "no ready model found for "
                f"region={region} crop_type={crop_type} task_type={task_type}"
            )
            logger.info("model_lookup_completed | model_exists=false")
            return ModelLookupResponse(
                model_exists=False,
                reason=reason,
            )

        logger.info(
            "model_lookup_completed | model_exists=true | model_id=%s | version=%s",
            model.id,
            model.model_version,
        )
        return ModelLookupResponse(
            model_exists=True,
            model_id=model.id,
            model_name=model.model_name,
            model_version=model.model_version,
            artifact_uri=model.artifact_uri,
            metrics_json=model.metrics_json,
            status=model.status,
            description=model.description,
        )

    def set_model_status(
        self,
        model_id: int,
        request: ModelStatusUpdateRequest,
    ) -> ModelResponse:
        """Update model status with basic lifecycle validation."""
        logger.info(
            "model_status_update_started | model_id=%s | target_status=%s",
            model_id,
            request.status.value,
        )
        model = self._repository.get_model_by_id(model_id)
        if model is None:
            logger.warning("model_status_update_failed | model_id=%s | reason=not_found", model_id)
            raise ModelNotFoundError(f"Model with id={model_id} was not found.")

        current_status = model.status
        if current_status == request.status:
            logger.info("model_status_update_noop | model_id=%s", model_id)
            return ModelResponse.model_validate(model)

        allowed_targets = self._allowed_transitions[current_status]
        if request.status not in allowed_targets:
            logger.warning(
                "model_status_update_failed | model_id=%s | from=%s | to=%s",
                model_id,
                current_status.value,
                request.status.value,
            )
            raise ModelValidationError(
                f"Invalid status transition from {current_status.value} to {request.status.value}."
            )

        updated_model = self._repository.update_model_status(model_id, request.status)
        self._repository.commit()
        if updated_model is None:
            raise ModelNotFoundError(f"Model with id={model_id} was not found.")
        logger.info(
            "model_status_update_succeeded | model_id=%s | status=%s",
            model_id,
            updated_model.status.value,
        )
        return ModelResponse.model_validate(updated_model)

    def list_registered_models(
        self,
        *,
        region: str | None = None,
        crop_type: str | None = None,
        task_type: str | None = None,
        status: ModelStatus | None = None,
    ) -> ModelListResponse:
        """List registered models with basic filters."""
        logger.info(
            "model_list_started | region=%s | crop_type=%s | task_type=%s | status=%s",
            region,
            crop_type,
            task_type,
            status.value if status else None,
        )
        models = self._repository.list_models(
            region=region,
            crop_type=crop_type,
            task_type=task_type,
            status=status,
        )
        logger.info("model_list_succeeded | total=%s", len(models))
        return ModelListResponse(
            total=len(models),
            items=[ModelResponse.model_validate(model) for model in models],
        )
