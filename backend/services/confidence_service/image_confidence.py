"""Heuristic image confidence scoring."""

from __future__ import annotations

from shared.inference_sanity import inspect_mask_artifact
from services.confidence_service.schemas import ImageConfidenceInput, SubConfidenceResult


def score_image_confidence(payload: ImageConfidenceInput) -> SubConfidenceResult:
    """Score image confidence from model output and geometric signal."""
    score = max(0.0, min(1.0, payload.model_confidence))
    reasons = ["started from model confidence"]
    if payload.polygon_count > 0:
        score = min(1.0, score + 0.03)
        reasons.append("slightly increased because polygons were produced")
    if payload.affected_area <= 0:
        score = max(0.0, score - 0.08)
        reasons.append("reduced because affected area is zero or negative")

    sanity_result = inspect_mask_artifact(payload.mask_uri)
    warnings = list(sanity_result.warnings)
    if sanity_result.available:
        reasons.append(f"mask coverage was {sanity_result.positive_ratio:.2%}")
        if sanity_result.positive_pixels > 0 and sanity_result.positive_ratio == 1.0:
            score = max(0.0, score - 0.08)
            reasons.append("reduced because every valid pixel was marked positive")
        if sanity_result.positive_pixels > 0 and sanity_result.positive_ratio >= 0.98:
            score = max(0.0, score - 0.28)
            reasons.append("reduced because mask coverage is near-total")
        if (
            sanity_result.positive_pixels > 0
            and sanity_result.positive_ratio == 1.0
            and sanity_result.unique_value_count == 1
        ):
            score = max(0.0, score - 0.12)
            reasons.append("reduced because the mask collapses to a single positive value")
        if payload.task_type == "baldness_detection" and sanity_result.positive_ratio >= 0.9:
            score = max(0.0, score - 0.14)
            reasons.append(
                "reduced further because near-total baldness coverage is suspicious for this task"
            )
    elif payload.mask_uri:
        score = max(0.0, score - 0.12)
        reasons.append("reduced because the mask artifact could not be inspected")

    label = _label(score)
    return SubConfidenceResult(
        score=round(score, 4),
        label=label,
        reason="; ".join(reasons),
        warnings=warnings,
    )


def _label(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.55:
        return "medium"
    return "low"
