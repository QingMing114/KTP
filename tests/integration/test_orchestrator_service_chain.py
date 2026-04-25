"""Integration test for the orchestrator service chain."""

from __future__ import annotations

from apps.orchestrator.main import run_workflow_request
from shared.schemas.orchestrator import WorkflowRequest


def test_orchestrator_service_chain_runs_real_local_clients(
    integration_runtime: dict[str, object],
) -> None:
    response = run_workflow_request(
        WorkflowRequest(
            request_id="req-orch-chain-001",
            user_query="Assess wheat health in Henan and provide a report with confidence.",
            region="henan",
            crop_type="wheat",
            task_type="crop_health_detection",
            use_mock=True,
        )
    )

    final_state = response.final_state
    assert response.status == "completed"
    assert final_state["inference_result"] is not None
    assert final_state["rag_result"] is not None
    assert final_state["report_result"] is not None
    assert final_state["confidence_result"] is not None
    assert final_state["visualization_result"] is not None
