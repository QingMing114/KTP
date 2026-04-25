"""Fusion logic for confidence sub-scores."""

from __future__ import annotations

from services.confidence_service.config import (
    ConfidenceServiceConfig,
    get_confidence_service_config,
)
from services.confidence_service.schemas import ConfidenceResult, SubConfidenceResult


def fuse_confidence_results(
    *,
    image_result: SubConfidenceResult,
    text_result: SubConfidenceResult,
    workflow_result: SubConfidenceResult,
    config: ConfidenceServiceConfig | None = None,
) -> ConfidenceResult:
    """Fuse the three sub-scores into a final confidence result."""
    resolved_config = config or get_confidence_service_config()
    weights = [
        resolved_config.image_confidence_weight,
        resolved_config.text_confidence_weight,
        resolved_config.workflow_confidence_weight,
    ]
    if any(weight < 0 for weight in weights):
        raise ValueError("confidence weights must be non-negative")
    total_weight = sum(weights)
    if total_weight <= 0:
        raise ValueError("confidence weights must sum to a positive value")

    final_confidence = (
        (image_result.score * resolved_config.image_confidence_weight)
        + (text_result.score * resolved_config.text_confidence_weight)
        + (workflow_result.score * resolved_config.workflow_confidence_weight)
    ) / total_weight
    final_confidence = round(final_confidence, 4)
    final_label = _label(final_confidence)
    warnings: list[str] = []
    if image_result.warnings:
        warnings.append(f"image: {'; '.join(image_result.warnings)}")
    if text_result.warnings:
        warnings.append(f"text: {'; '.join(text_result.warnings)}")
    if workflow_result.warnings:
        warnings.append(f"workflow: {'; '.join(workflow_result.warnings)}")
    return ConfidenceResult(
        image_confidence=image_result,
        text_confidence=text_result,
        workflow_confidence=workflow_result,
        final_confidence=final_confidence,
        final_label=final_label,
        explanation=(
            "overall result is derived from weighted image, text, and workflow confidence "
            f"signals with final label {final_label}"
            + (f"; warnings: {' | '.join(warnings)}" if warnings else "")
        ),
    )


def _label(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.55:
        return "medium"
    return "low"
