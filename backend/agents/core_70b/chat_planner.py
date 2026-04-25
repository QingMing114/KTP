"""Bounded chat planner for the self-scheduling runtime."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from agents.core_70b.chat_prompts import CHAT_PLANNER_SYSTEM_PROMPT
from infra.llm.provider import AgentLLMError, AgentLLMProvider
from shared.request_normalization import (
    detect_crop_type_from_text,
    detect_region_from_text,
    detect_task_type_from_text,
    normalize_crop_type,
    normalize_region,
    normalize_task_type,
)
from shared.schemas.agent_runtime import PlannerDecision, PlannerStep, ToolObservation, ToolSpec

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatPlannerConfig:
    """Configuration for bounded chat planning."""

    default_task_type: str = "crop_health_detection"


class HeuristicChatPlanner:
    """Deterministic fallback planner for bounded chat routing."""

    def __init__(self, config: ChatPlannerConfig | None = None) -> None:
        self._config = config or ChatPlannerConfig()

    def plan(
        self,
        *,
        user_message: str,
        available_tools: list[ToolSpec],
        conversation_history: str = "",
        region: str | None = None,
        crop_type: str | None = None,
        task_type: str | None = None,
        tool_observation: ToolObservation | None = None,
        replan_count: int = 0,
    ) -> PlannerDecision:
        del conversation_history
        text = user_message.lower()
        normalized_region = normalize_region(region) or detect_region_from_text(user_message)
        normalized_crop = normalize_crop_type(crop_type) or detect_crop_type_from_text(user_message)
        normalized_task = (
            normalize_task_type(task_type)
            or detect_task_type_from_text(user_message, default=self._config.default_task_type)
            or self._config.default_task_type
        )

        if replan_count > 0 and tool_observation and not tool_observation.success:
            return PlannerDecision(
                route="abstain",
                reasoning_summary=(
                    f"Previous tool call `{tool_observation.tool_name}` failed; "
                    "bounded runtime stops after the allowed replan."
                ),
                region=normalized_region,
                crop_type=normalized_crop,
                task_type=normalized_task,
                need_training=False,
                need_rag=False,
                need_report=False,
                need_confidence=False,
                steps=[],
            )

        if self._looks_like_general_knowledge(text):
            return PlannerDecision(
                route="direct_answer",
                reasoning_summary="General knowledge question; direct answer is sufficient.",
                answer=user_message,
                region=normalized_region,
                crop_type=normalized_crop,
                task_type=normalized_task,
                need_training=False,
                need_rag=False,
                need_report=False,
                need_confidence=False,
                steps=[],
            )

        if self._needs_workflow(text, normalized_task):
            return PlannerDecision(
                route="tool_sequence",
                reasoning_summary="Remote sensing analysis or artifact generation requires workflow execution.",
                region=normalized_region,
                crop_type=normalized_crop,
                task_type=normalized_task,
                need_training="训练" in user_message or "train" in text or "retrain" in text,
                need_rag=False,
                need_report=self._needs_report(text),
                need_confidence=self._needs_confidence(text),
                steps=[
                    PlannerStep(
                        step_id="step-1",
                        action="call_tool",
                        tool_name=self._pick_tool_name(
                            preferred="run_remote_sensing_workflow",
                            available_tools=available_tools,
                        ),
                        purpose="Execute the bounded remote sensing workflow for structured analysis.",
                        tool_input={
                            "message": user_message,
                            "region": normalized_region,
                            "crop_type": normalized_crop,
                            "task_type": normalized_task,
                            "extra_params": {
                                "agent_plan": {
                                    "region": normalized_region,
                                    "crop_type": normalized_crop,
                                    "task_type": normalized_task,
                                    "need_training": "训练" in user_message or "train" in text or "retrain" in text,
                                    "need_rag": False,
                                    "need_report": self._needs_report(text),
                                    "need_confidence": self._needs_confidence(text),
                                }
                            },
                        },
                    )
                ],
            )

        if self._needs_rag(text):
            return PlannerDecision(
                route="tool_sequence",
                reasoning_summary="The answer should be grounded in local knowledge or explicit sources.",
                region=normalized_region,
                crop_type=normalized_crop,
                task_type=normalized_task,
                need_training=False,
                need_rag=True,
                need_report=False,
                need_confidence=False,
                steps=[
                    PlannerStep(
                        step_id="step-1",
                        action="call_tool",
                        tool_name=self._pick_tool_name(
                            preferred="rag_search",
                            available_tools=available_tools,
                        ),
                        purpose="Retrieve local knowledge snippets and sources.",
                        tool_input={
                            "user_query": user_message,
                            "region": normalized_region,
                            "crop_type": normalized_crop,
                            "task_type": normalized_task,
                            "top_k": 5,
                            "context": {},
                        },
                    )
                ],
            )

        return PlannerDecision(
            route="direct_answer",
            reasoning_summary="No workflow or retrieval need detected; answer directly.",
            answer=user_message,
            region=normalized_region,
            crop_type=normalized_crop,
            task_type=normalized_task,
            need_training=False,
            need_rag=False,
            need_report=False,
            need_confidence=False,
            steps=[],
        )

    @staticmethod
    def _looks_like_general_knowledge(text: str) -> bool:
        general_tokens = (
            "有什么区别",
            "区别",
            "what is",
            "difference",
            "解释",
            "介绍",
            "vscode",
            "codex",
            "claude",
            "ndvi",
            "evi",
        )
        blocking_tokens = (
            "检测",
            "识别",
            "分析",
            "workflow",
            "报告",
            "置信度",
            "可视化",
            "影像",
            "图像",
            "病害",
            "反演",
        )
        return any(token in text for token in general_tokens) and not any(
            token in text for token in blocking_tokens
        )

    @staticmethod
    def _needs_report(text: str) -> bool:
        return any(token in text for token in ("报告", "report", "summary", "汇总"))

    @staticmethod
    def _needs_confidence(text: str) -> bool:
        return any(token in text for token in ("置信度", "confidence"))

    @classmethod
    def _needs_workflow(cls, text: str, task_type: str | None) -> bool:
        workflow_tokens = (
            "分析",
            "检测",
            "识别",
            "分割",
            "反演",
            "workflow",
            "报告",
            "置信度",
            "可视化",
            "影像",
            "图像",
            "病害",
            "长势",
        )
        return task_type in {
            "crop_health_detection",
            "yield_estimation",
            "lai_inversion",
            "land_cover_analysis",
            "baldness_detection",
        } and any(token in text for token in workflow_tokens)

    @staticmethod
    def _needs_rag(text: str) -> bool:
        rag_tokens = ("知识库", "资料", "来源", "source", "sources", "文献", "根据资料")
        return any(token in text for token in rag_tokens)

    @staticmethod
    def _pick_tool_name(*, preferred: str, available_tools: list[ToolSpec]) -> str:
        for tool in available_tools:
            if tool.name == preferred:
                return tool.name
        return preferred


class ChatPlanner:
    """LLM-first bounded chat planner with heuristic fallback."""

    def __init__(
        self,
        *,
        llm_provider: AgentLLMProvider | None = None,
        config: ChatPlannerConfig | None = None,
    ) -> None:
        self._heuristic = HeuristicChatPlanner(config=config)
        self._llm_provider = llm_provider

    def plan(
        self,
        *,
        user_message: str,
        available_tools: list[ToolSpec],
        conversation_history: str = "",
        region: str | None = None,
        crop_type: str | None = None,
        task_type: str | None = None,
        tool_observation: ToolObservation | None = None,
        replan_count: int = 0,
    ) -> PlannerDecision:
        fallback = self._heuristic.plan(
            user_message=user_message,
            available_tools=available_tools,
            conversation_history=conversation_history,
            region=region,
            crop_type=crop_type,
            task_type=task_type,
            tool_observation=tool_observation,
            replan_count=replan_count,
        )
        if self._llm_provider is None:
            return self._postprocess_decision(fallback, available_tools=available_tools)

        try:
            decision = self._llm_provider.generate_structured(
                system_prompt=CHAT_PLANNER_SYSTEM_PROMPT,
                user_prompt=(
                    "Return a planning JSON object for the current chat turn.\n"
                    "Available tools (JSON):\n"
                    f"{json.dumps([tool.model_dump() for tool in available_tools], ensure_ascii=False, sort_keys=True)}\n\n"
                    "Conversation history:\n"
                    f"{conversation_history or '无'}\n\n"
                    "Previous tool observation:\n"
                    f"{json.dumps(tool_observation.model_dump(), ensure_ascii=False, sort_keys=True) if tool_observation else '无'}\n\n"
                    "Current replan count:\n"
                    f"{replan_count}\n\n"
                    "Current explicit metadata:\n"
                    f"{json.dumps({'region': region, 'crop_type': crop_type, 'task_type': task_type}, ensure_ascii=False, sort_keys=True)}\n\n"
                    "User message:\n"
                    f"{user_message}"
                ),
                response_model=PlannerDecision,
            )
        except AgentLLMError as exc:
            logger.warning("chat_planner_llm_fallback | detail=%s", str(exc))
            return self._postprocess_decision(fallback, available_tools=available_tools)

        return self._postprocess_decision(decision, available_tools=available_tools, fallback=fallback)

    def _postprocess_decision(
        self,
        decision: PlannerDecision,
        *,
        available_tools: list[ToolSpec],
        fallback: PlannerDecision | None = None,
    ) -> PlannerDecision:
        fallback = fallback or decision
        tool_names = {tool.name for tool in available_tools}
        normalized_steps: list[PlannerStep] = []
        source_steps = decision.steps or fallback.steps
        for index, step in enumerate(source_steps, start=1):
            tool_name = step.tool_name
            if step.action == "call_tool" and tool_name not in tool_names:
                fallback_tool = fallback.steps[index - 1].tool_name if len(fallback.steps) >= index else None
                if fallback_tool in tool_names:
                    tool_name = fallback_tool
            normalized_steps.append(
                PlannerStep(
                    step_id=step.step_id or f"step-{index}",
                    action=step.action,
                    tool_name=tool_name,
                    purpose=step.purpose,
                    tool_input=step.tool_input,
                )
            )

        route = decision.route
        if route == "tool_sequence" and not normalized_steps:
            route = fallback.route

        return PlannerDecision(
            route=route,
            reasoning_summary=decision.reasoning_summary or fallback.reasoning_summary,
            answer=decision.answer if route == "direct_answer" else None,
            region=normalize_region(decision.region) or fallback.region,
            crop_type=normalize_crop_type(decision.crop_type) or fallback.crop_type,
            task_type=normalize_task_type(decision.task_type) or fallback.task_type,
            need_training=decision.need_training if decision.need_training is not None else fallback.need_training,
            need_rag=decision.need_rag if decision.need_rag is not None else fallback.need_rag,
            need_report=decision.need_report if decision.need_report is not None else fallback.need_report,
            need_confidence=(
                decision.need_confidence if decision.need_confidence is not None else fallback.need_confidence
            ),
            steps=normalized_steps,
        )
