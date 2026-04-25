"""Repository layer for registered model persistence."""

from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from services.model_registry.models import RegisteredModel
from services.model_registry.schemas import ModelStatus


class ModelRegistryRepository:
    """Database access methods for registered models."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def commit(self) -> None:
        """Commit the active transaction."""
        self._session.commit()

    def rollback(self) -> None:
        """Rollback the active transaction."""
        self._session.rollback()

    def create_model(
        self,
        *,
        region: str,
        crop_type: str,
        task_type: str,
        model_name: str,
        model_version: str,
        artifact_uri: str,
        metrics_json: dict | None,
        status: ModelStatus,
        description: str | None,
    ) -> RegisteredModel:
        model = RegisteredModel(
            region=region,
            crop_type=crop_type,
            task_type=task_type,
            model_name=model_name,
            model_version=model_version,
            artifact_uri=artifact_uri,
            metrics_json=metrics_json,
            status=status,
            description=description,
        )
        self._session.add(model)
        self._session.flush()
        self._session.refresh(model)
        return model

    def get_model_by_id(self, model_id: int) -> RegisteredModel | None:
        return self._session.get(RegisteredModel, model_id)

    def find_models(
        self,
        region: str,
        crop_type: str,
        task_type: str,
    ) -> list[RegisteredModel]:
        stmt = (
            select(RegisteredModel)
            .where(
                RegisteredModel.region == region,
                RegisteredModel.crop_type == crop_type,
                RegisteredModel.task_type == task_type,
            )
            .order_by(RegisteredModel.created_at.desc(), RegisteredModel.id.desc())
        )
        return list(self._session.scalars(stmt))

    def get_latest_ready_model(
        self,
        region: str,
        crop_type: str,
        task_type: str,
    ) -> RegisteredModel | None:
        stmt = (
            select(RegisteredModel)
            .where(
                RegisteredModel.region == region,
                RegisteredModel.crop_type == crop_type,
                RegisteredModel.task_type == task_type,
                RegisteredModel.status == ModelStatus.READY,
            )
            .order_by(RegisteredModel.created_at.desc(), RegisteredModel.id.desc())
            .limit(1)
        )
        return self._session.scalar(stmt)

    def update_model_status(
        self,
        model_id: int,
        status: ModelStatus,
    ) -> RegisteredModel | None:
        model = self.get_model_by_id(model_id)
        if model is None:
            return None
        model.status = status
        self._session.flush()
        self._session.refresh(model)
        return model

    def list_models(
        self,
        *,
        region: str | None = None,
        crop_type: str | None = None,
        task_type: str | None = None,
        status: ModelStatus | None = None,
    ) -> list[RegisteredModel]:
        stmt: Select[tuple[RegisteredModel]] = select(RegisteredModel)
        if region is not None:
            stmt = stmt.where(RegisteredModel.region == region)
        if crop_type is not None:
            stmt = stmt.where(RegisteredModel.crop_type == crop_type)
        if task_type is not None:
            stmt = stmt.where(RegisteredModel.task_type == task_type)
        if status is not None:
            stmt = stmt.where(RegisteredModel.status == status)
        stmt = stmt.order_by(RegisteredModel.created_at.desc(), RegisteredModel.id.desc())
        return list(self._session.scalars(stmt))
