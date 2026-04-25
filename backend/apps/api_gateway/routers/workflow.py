"""Workflow lookup routes for the API gateway."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from apps.api_gateway.clients.orchestrator_client import LocalOrchestratorClient
from apps.api_gateway.routers.dependencies import get_orchestrator_client
from apps.api_gateway.schemas.workflow import WorkflowStatusResponse

router = APIRouter(tags=["workflow"])


@router.get(
    "/workflow/{request_id}",
    response_model=WorkflowStatusResponse,
    summary="Lookup a workflow result by request id",
)
async def get_workflow_status(
    request_id: str,
    client: LocalOrchestratorClient = Depends(get_orchestrator_client),
) -> WorkflowStatusResponse:
    """Return the latest cached workflow result for a request id."""
    response = client.get_workflow(request_id)
    if response is None:
        return WorkflowStatusResponse(
            request_id=request_id,
            found=False,
            workflow_status=None,
            result=None,
            message="workflow result not found",
        )
    return WorkflowStatusResponse(
        request_id=request_id,
        found=True,
        workflow_status=response.status,
        result=response.final_state,
        message="workflow result found",
    )
