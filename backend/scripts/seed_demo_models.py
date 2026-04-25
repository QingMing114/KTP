"""Seed demo models and knowledge for local integration runs."""

from __future__ import annotations

import os

from services.model_registry.db import create_engine_for_url, create_session_factory, init_db
from services.model_registry.repository import ModelRegistryRepository
from services.model_registry.schemas import ModelRegisterRequest, ModelStatus
from services.model_registry.service import ModelRegistryService
from services.rag_service.config import get_rag_service_config
from services.rag_service.schemas import DocumentIngestRequest
from services.rag_service.service import RAGService


def seed_demo_assets(
    *,
    database_url: str,
    artifact_uri: str = "mock://models/wheat-health-segmentation/demo-v1",
) -> None:
    """Seed a demo ready model and a small RAG knowledge base."""
    engine = create_engine_for_url(database_url)
    init_db(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        service = ModelRegistryService(ModelRegistryRepository(session))
        try:
            service.register_model(
                ModelRegisterRequest(
                    region="henan",
                    crop_type="wheat",
                    task_type="crop_health_detection",
                    model_name="wheat-health-segmentation",
                    model_version="demo-v1",
                    artifact_uri=artifact_uri,
                    metrics_json={"miou": 0.88},
                    status=ModelStatus.READY,
                )
            )
        except Exception:
            pass
    engine.dispose()

    rag_service = RAGService(config=get_rag_service_config())
    for document in [
        DocumentIngestRequest(
            document_id="doc-demo-henan-wheat",
            title="Henan Wheat Stress Guide",
            source="local://knowledge/henan-wheat",
            text=(
                "Henan wheat health monitoring often considers drought stress, "
                "disease pressure, and agronomic response plans."
            ),
            metadata={
                "region": "henan",
                "crop_type": "wheat",
                "task_type": "crop_health_detection",
            },
        )
    ]:
        try:
            rag_service.ingest_document(document)
        except Exception:
            continue


if __name__ == "__main__":
    seed_demo_assets(
        database_url=os.environ.get("ORCHESTRATOR_DATABASE_URL", "sqlite:///./demo_registry.db")
    )
