"""Heuristic workflow confidence scoring."""

from __future__ import annotations

from services.confidence_service.schemas import SubConfidenceResult, WorkflowConfidenceInput


def score_workflow_confidence(payload: WorkflowConfidenceInput) -> SubConfidenceResult:
    """Score workflow confidence from process stability and branch outcome."""
    score = 0.85 if payload.model_exists else 0.72
    if payload.training_triggered:
        score -= 0.12
    if payload.error_count > 0:
        score -= min(0.4, payload.error_count * 0.15)
    if payload.status != "completed":
        score -= 0.08
    score = max(0.0, min(1.0, score))
    label = _label(score)
    return SubConfidenceResult(
        score=round(score, 4),
        label=label,
        reason=(
            "workflow confidence reflects branch stability, training fallback usage, "
            "error count, and final workflow status"
        ),
    )


def _label(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.55:
        return "medium"
    return "low"
