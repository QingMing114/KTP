"""Heuristic text/RAG confidence scoring."""

from __future__ import annotations

from services.confidence_service.schemas import SubConfidenceResult, TextConfidenceInput


def score_text_confidence(payload: TextConfidenceInput) -> SubConfidenceResult:
    """Score text confidence from retrieval availability and quality."""
    source_component = min(payload.retrieved_source_count, 4) * 0.12
    retrieval_component = max(0.0, min(1.0, payload.average_retrieval_score)) * 0.4
    summary_component = 0.18 if payload.has_rag_summary else 0.0
    score = min(1.0, 0.1 + source_component + retrieval_component + summary_component)
    label = _label(score)
    return SubConfidenceResult(
        score=round(score, 4),
        label=label,
        reason=(
            "text confidence is based on retrieved source count, average retrieval score, "
            "and whether a usable summary is available"
        ),
    )


def _label(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.55:
        return "medium"
    return "low"
