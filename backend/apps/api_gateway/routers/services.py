"""Internal service health aggregation routes for the API gateway."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Request

from apps.api_gateway.schemas.workflow import ServiceHealthResponse

router = APIRouter(tags=["services"])


def _get_or_create_service_apps(request: Request) -> dict[str, object]:
    if not hasattr(request.app.state, "service_health_apps"):
        from apps.orchestrator.config import get_orchestrator_runtime_config
        from services.confidence_service.main import create_app as create_confidence_app
        from services.inference_service.main import create_app as create_inference_app
        from services.model_registry.main import create_app as create_model_registry_app
        from services.rag_service.main import create_app as create_rag_app
        from services.report_service.main import create_app as create_report_app
        from services.training_service.main import create_app as create_training_app
        from services.visualization_service.main import create_app as create_visualization_app

        orchestrator_config = get_orchestrator_runtime_config()
        request.app.state.service_health_apps = {
            "model_registry": create_model_registry_app(database_url=orchestrator_config.database_url),
            "training_service": create_training_app(),
            "inference_service": create_inference_app(),
            "rag_service": create_rag_app(),
            "report_service": create_report_app(),
            "confidence_service": create_confidence_app(),
            "visualization_service": create_visualization_app(),
        }
    return request.app.state.service_health_apps


@router.get(
    "/services/health",
    response_model=ServiceHealthResponse,
    summary="Aggregate internal service health",
)
async def get_services_health(request: Request) -> ServiceHealthResponse:
    """Return aggregated health snapshots for internal services."""
    service_apps = _get_or_create_service_apps(request)
    results: dict[str, dict[str, object]] = {}
    for service_name, app in service_apps.items():
        results[service_name] = await _call_health(app)
    return ServiceHealthResponse(success=True, services=results)


async def _call_health(app) -> dict[str, object]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        try:
            response = await client.get("/health")
            payload = response.json()
            return {
                "status": payload.get("status", "unknown"),
                "service": payload.get("service"),
                "checks": payload.get("checks", {}),
            }
        except Exception as exc:
            return {
                "status": "error",
                "detail": str(exc),
            }
