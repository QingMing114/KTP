"""Planner implementations with shared LLM support and heuristic fallback."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from infra.llm.provider import AgentLLMError, AgentLLMProvider
from agents.core_70b.prompts import PLANNER_SYSTEM_PROMPT
from shared.request_normalization import (
    detect_crop_type_from_text,
    detect_region_from_text,
    detect_task_type_from_text,
    normalize_crop_type,
    normalize_region,
    normalize_task_type,
)
from shared.schemas.planner import PlannerResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlannerConfig:
    """Configuration for the planner heuristics and LLM fallback."""

    default_task_type: str = "crop_health_detection"


class HeuristicRequestPlanner:
    """Convert user text into a structured planning result heuristically."""

    def __init__(self, config: PlannerConfig | None = None) -> None:
        self._config = config or PlannerConfig()

    def plan(self, user_query: str) -> PlannerResult:
        normalized = user_query.lower()
        task_type = self._detect_task_type(user_query)
        region = self._detect_region(user_query)
        crop_type = self._detect_crop_type(user_query)
        need_report = any(
            token in normalized for token in ["report", "summary", "报告", "汇总"]
        )
        need_rag = need_report or any(
            token in normalized
            for token in ["why", "explain", "reason", "建议", "解释", "recommend"]
        )
        need_confidence = True
        need_training = any(
            token in normalized
            for token in ["train", "fine-tune", "retrain", "训练", "微调"]
        )

        return PlannerResult(
            task_type=task_type,
            region=region,
            crop_type=crop_type,
            need_training=need_training,
            need_rag=need_rag,
            need_report=need_report,
            need_confidence=need_confidence,
            reasoning_summary=(
                "Deterministic planner extracted structured fields from the request "
                "and enabled downstream optional steps based on request intent."
            ),
        )

    def _detect_task_type(self, query: str) -> str:
        return detect_task_type_from_text(query, default=self._config.default_task_type) or self._config.default_task_type

    @staticmethod
    def _detect_region(query: str) -> str | None:
        return detect_region_from_text(query)

    @staticmethod
    def _detect_crop_type(query: str) -> str | None:
        return detect_crop_type_from_text(query)


class RequestPlanner:
    """Convert user text into a structured plan with LLM-first fallback logic."""

    def __init__(
        self,
        config: PlannerConfig | None = None,
        *,
        llm_provider: AgentLLMProvider | None = None,
    ) -> None:
        self._heuristic_planner = HeuristicRequestPlanner(config)
        self._llm_provider = llm_provider

    def plan(self, user_query: str) -> PlannerResult:
        heuristic_result = self._heuristic_planner.plan(user_query)
        if self._llm_provider is None:
            return heuristic_result

        try:
            llm_result = self._llm_provider.generate_structured(
                system_prompt=PLANNER_SYSTEM_PROMPT,
                user_prompt=(
                    "Convert the following user request into a planning JSON object.\n"
                    "Normalize region and crop type when possible.\n"
                    "Keep the reasoning summary concise.\n\n"
                    f"User request:\n{user_query}"
                ),
                response_model=PlannerResult,
            )
        except AgentLLMError as exc:
            logger.warning("planner_llm_fallback | detail=%s", str(exc))
            return heuristic_result

        normalized_task_type = self._normalize_task_type(llm_result.task_type)
        normalized_region = self._normalize_region(llm_result.region)
        normalized_crop_type = self._normalize_crop_type(llm_result.crop_type)
        return PlannerResult(
            task_type=normalized_task_type or heuristic_result.task_type,
            region=heuristic_result.region or normalized_region,
            crop_type=heuristic_result.crop_type or normalized_crop_type,
            need_training=llm_result.need_training or heuristic_result.need_training,
            need_rag=llm_result.need_rag or heuristic_result.need_rag,
            need_report=llm_result.need_report or heuristic_result.need_report,
            need_confidence=llm_result.need_confidence or heuristic_result.need_confidence,
            reasoning_summary=llm_result.reasoning_summary or heuristic_result.reasoning_summary,
        )

    @staticmethod
    def _normalize_task_type(task_type: str | None) -> str | None:
        return normalize_task_type(task_type)

    @staticmethod
    def _normalize_region(region: str | None) -> str | None:
        return normalize_region(region)

    @staticmethod
    def _normalize_crop_type(crop_type: str | None) -> str | None:
        return normalize_crop_type(crop_type)
