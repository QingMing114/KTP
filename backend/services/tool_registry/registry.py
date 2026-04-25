"""Bounded tool registry for the agent runtime."""

from __future__ import annotations

from functools import lru_cache

from shared.schemas.agent_runtime import ToolSpec


def list_tool_specs() -> list[ToolSpec]:
    """Return the full bounded tool catalog available to the agent runtime."""
    return list(_build_tool_registry())


def get_tool_spec(tool_name: str) -> ToolSpec | None:
    """Return one tool spec by name when registered."""
    for spec in _build_tool_registry():
        if spec.name == tool_name:
            return spec
    return None


def select_relevant_tools(
    *,
    user_message: str,
    task_type: str | None = None,
    limit: int = 5,
) -> list[ToolSpec]:
    """Retrieve a small bounded tool set for the current request."""
    normalized = user_message.lower()
    scored: list[tuple[int, ToolSpec]] = []
    for spec in _build_tool_registry():
        score = 0
        if task_type and task_type in spec.tags:
            score += 5
        for tag in spec.tags:
            if tag.lower() in normalized:
                score += 2
        for token in spec.name.lower().split("_"):
            if token and token in normalized:
                score += 1
        if score == 0 and spec.name == "run_remote_sensing_workflow":
            score = 1
        scored.append((score, spec))

    scored.sort(key=lambda item: (-item[0], item[1].name))
    selected = [spec for score, spec in scored if score > 0]
    if not selected:
        selected = list(_build_tool_registry())[:limit]
    return selected[:limit]


@lru_cache(maxsize=1)
def _build_tool_registry() -> tuple[ToolSpec, ...]:
    return (
        ToolSpec(
            name="direct_answer",
            description="Use the LLM itself to answer without external tools.",
            input_schema={
                "question": "string",
                "conversation_history": "string|null",
            },
            output_schema={
                "answer": "string",
            },
            when_to_use=(
                "Use for general knowledge or conversational questions when no local knowledge "
                "retrieval or remote sensing workflow execution is required."
            ),
            usage_rules=[
                "Do not fabricate external evidence or workflow outputs.",
                "Prefer this for broad explanatory questions such as index differences or conceptual explanations.",
            ],
            tags=["chat", "general_knowledge", "direct_answer"],
            risk_level="low",
        ),
        ToolSpec(
            name="rag_search",
            description="Retrieve local knowledge snippets for evidence-backed answers.",
            input_schema={
                "user_query": "string",
                "task_type": "string|null",
                "region": "string|null",
                "crop_type": "string|null",
                "top_k": "integer|null",
                "context": "object",
            },
            output_schema={
                "summary": "string",
                "sources": "array[string]",
                "results": "array[object]",
            },
            when_to_use=(
                "Use when the answer should be grounded in local knowledge snippets or the user explicitly asks for sources."
            ),
            usage_rules=[
                "RAG provides supporting evidence only and must not override authoritative inference outputs.",
                "Return traceable sources whenever retrieval succeeds.",
            ],
            tags=["rag", "knowledge", "sources", "qa"],
            risk_level="low",
        ),
        ToolSpec(
            name="run_remote_sensing_workflow",
            description="Invoke the bounded remote sensing workflow through the orchestrator.",
            input_schema={
                "message": "string",
                "region": "string|null",
                "crop_type": "string|null",
                "task_type": "string|null",
                "image_path": "string|null",
                "use_mock": "boolean|null",
                "extra_params": "object",
            },
            output_schema={
                "workflow_status": "string",
                "inference_result": "object|null",
                "rag_result": "object|null",
                "report_result": "object|null",
                "confidence_result": "object|null",
                "visualization_result": "object|null",
            },
            when_to_use=(
                "Use when the user requests remote sensing analysis, detection, inference, report generation, "
                "confidence output, or visualization."
            ),
            usage_rules=[
                "The workflow remains bounded by the production orchestration contract.",
                "If training is required, the workflow may return training-triggered instead of a fake final inference.",
            ],
            tags=[
                "workflow",
                "remote_sensing",
                "report",
                "confidence",
                "visualization",
                "crop_health_detection",
                "yield_estimation",
                "lai_inversion",
                "land_cover_analysis",
                "baldness_detection",
            ],
            risk_level="medium",
        ),
    )
