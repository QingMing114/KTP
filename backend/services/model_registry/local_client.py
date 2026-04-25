"""Local client wrapper around the model registry service layer."""

from __future__ import annotations

import logging

from services.model_registry.db import (
    create_engine_for_url,
    create_session_factory,
    init_db,
    redact_database_url,
)
from services.model_registry.repository import ModelRegistryRepository
from services.model_registry.schemas import ModelLookupResponse
from services.model_registry.service import ModelRegistryService

logger = logging.getLogger(__name__)


class LocalModelRegistryLookupClient:
    """Look up ready models directly against the registry database."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._engine = create_engine_for_url(database_url)
        self._session_factory = create_session_factory(self._engine)
        init_db(self._engine)

    def lookup_model(
        self,
        *,
        region: str,
        crop_type: str,
        task_type: str,
    ) -> ModelLookupResponse:
        """Resolve the latest ready model for the workflow lookup."""
        logger.info(
            "local_model_registry_lookup_started | region=%s | crop_type=%s | task_type=%s",
            region,
            crop_type,
            task_type,
        )
        with self._session_factory() as session:
            service = ModelRegistryService(ModelRegistryRepository(session))
            result = service.lookup_model(
                region=region,
                crop_type=crop_type,
                task_type=task_type,
            )
        logger.info(
            "local_model_registry_lookup_completed | model_exists=%s | database_url=%s",
            result.model_exists,
            redact_database_url(self._database_url),
        )
        return result

    def close(self) -> None:
        """Dispose the underlying engine when the client is no longer needed."""
        self._engine.dispose()
