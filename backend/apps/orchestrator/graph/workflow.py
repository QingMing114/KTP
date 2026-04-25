"""LangGraph workflow definition for the orchestrator scaffold."""

from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from apps.orchestrator.graph.nodes.build_report import build_report_node
from apps.orchestrator.graph.nodes.build_visualization import build_visualization_node
from apps.orchestrator.graph.nodes.check_model_registry import (
    check_model_registry_node,
    route_after_model_check,
)
from apps.orchestrator.graph.nodes.evaluate_confidence import (
    evaluate_confidence_node,
)
from apps.orchestrator.graph.nodes.parse_request import parse_request_node
from apps.orchestrator.graph.nodes.run_inference import run_inference_node
from apps.orchestrator.graph.nodes.run_rag import run_rag_node
from apps.orchestrator.graph.nodes.trigger_training import trigger_training_node
from apps.orchestrator.graph.states import WorkflowState


def build_workflow():
    """Build and compile the main LangGraph workflow."""
    builder = StateGraph(WorkflowState)

    builder.add_node("parse_request", parse_request_node)
    builder.add_node("check_model_registry", check_model_registry_node)
    builder.add_node("trigger_training", trigger_training_node)
    builder.add_node("run_inference", run_inference_node)
    builder.add_node("run_rag", run_rag_node)
    builder.add_node("build_report", build_report_node)
    builder.add_node("evaluate_confidence", evaluate_confidence_node)
    builder.add_node("build_visualization", build_visualization_node)

    builder.add_edge(START, "parse_request")
    builder.add_edge("parse_request", "check_model_registry")
    builder.add_conditional_edges(
        "check_model_registry",
        route_after_model_check,
        {
            "run_inference": "run_inference",
            "trigger_training": "trigger_training",
        },
    )
    builder.add_edge("run_inference", "run_rag")
    builder.add_edge("trigger_training", "run_rag")
    builder.add_edge("run_rag", "build_report")
    builder.add_edge("build_report", "evaluate_confidence")
    builder.add_edge("evaluate_confidence", "build_visualization")
    builder.add_edge("build_visualization", END)

    return builder.compile()


@lru_cache(maxsize=1)
def get_workflow():
    """Return a cached compiled workflow instance."""
    return build_workflow()
