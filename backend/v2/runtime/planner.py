from __future__ import annotations

import json
from typing import Iterable

from infra.llm.provider import AgentLLMError, AgentLLMProvider
from shared.request_normalization import (
    detect_crop_type_from_text,
    detect_region_from_text,
    detect_task_type_from_text,
    extract_image_path_from_text,
)
from v2.shared.schemas import AgentStepV2, AgentToolCallV2, RequestContextV2, SessionMessage, ToolSpecV2


class ChatFirstPlanner:
    """Structured chat-first planner that delegates step selection to the shared LLM."""

    def __init__(self, *, llm_provider: AgentLLMProvider | None) -> None:
        self._llm_provider = llm_provider

    def plan(
        self,
        *,
        message: str,
        visible_tools: list[ToolSpecV2],
        request_context: RequestContextV2,
        recent_messages: list[SessionMessage],
        tool_history: list[dict[str, object]],
        last_task_digest: dict[str, object] | None,
    ) -> AgentStepV2:
        if self._llm_provider is None:
            raise AgentLLMError("chat_first_planner_requires_llm_provider")

        step = self._llm_provider.generate_structured(
            system_prompt=self._build_system_prompt(request_context=request_context),
            user_prompt=self._build_user_prompt(
                message=message,
                visible_tools=visible_tools,
                request_context=request_context,
                recent_messages=recent_messages,
                tool_history=tool_history,
                last_task_digest=last_task_digest,
            ),
            response_model=AgentStepV2,
        )
        return self._normalize_step(
            step=step,
            message=message,
            request_context=request_context,
            visible_tools=visible_tools,
        )

    @staticmethod
    def _build_system_prompt(*, request_context: RequestContextV2) -> str:
        task_mode_rules = (
            "conversation_mode=task: 用户有明确的任务需求，优先选择最匹配的工具执行，不要选无关工具。"
            if request_context.conversation_mode == "task"
            else "conversation_mode=chat: 优先直接回答，确实需要外部能力时才调用工具。"
        )
        return (
            "你是 KTP Chat-First Agent 的 planner。"
            "严格输出一个符合 AgentStepV2 的 JSON 对象。"
            "action 只能是 reply、clarify、call_tools、fail。"
            "【路由决策】根据用户意图选择最合适的工具，不要机械地匹配关键词："
            "闲聊/问候/身份/一般知识/不需要工具 → reply；"
            "需要工具才能完成 → call_tools；"
            "缺关键输入 → clarify。"
            "【工具选择指南】理解用户意图后选择最匹配的工具："
            "ktp.analysis_pipeline — 完整遥感分析流程（推理+报告+置信度+可视化一步到位）"
            "ktp.lookup_model_registry — 仅查询可用模型"
            "ktp.run_inference_workflow — 仅运行推理"
            "ktp.build_report — 仅生成报告"
            "ktp.evaluate_confidence — 仅评估置信度"
            "ktp.build_visualization — 仅生成可视化"
            "ktp.explain_knowledge — 知识概念解释"
            "ktp.retrieve_knowledge — 检索知识来源"
            "knowledge.search_local — 本地知识搜索"
            "ktp.trigger_training — 训练模型"
            "prosail.simulation — 植被光谱模拟"
            "prosail.build_lut / prosail.load_lut — 查找表构建/加载"
            "prosail.invert_lai — 单像素LAI反演"
            "prosail.invert_lai_tif — 批量LAI反演(tif)"
            "apsim.crop_simulation — APSIM作物生长模拟"
            "workspace.search / workspace.read_file / workspace.write — 工作区文件操作"
            "【选择原则】"
            "1. 用户需要端到端分析 → ktp.analysis_pipeline"
            "2. 用户只需要某个步骤 → 选对应子工具"
            "3. 用户明确指定工具 → 按用户要求选择"
            "4. 用户需要LAI反演且要报告 → ktp.analysis_pipeline"
            "5. 用户只需LAI数值 → prosail.invert_lai 或 prosail.invert_lai_tif"
            "6. 用户需要作物模拟 → apsim.crop_simulation"
            "7. 不要因为提到领域词就盲目调工具"
            "reply/clarify/fail 要写 response_message。call_tools 要写 tool_calls。"
            "默认使用用户语言，简洁自然。"
            "【防循环】tool_history 中已有相同工具成功结果时必须 reply，绝不重复调用。"
            f"{task_mode_rules}"
        )

    @staticmethod
    def _build_user_prompt(
        *,
        message: str,
        visible_tools: list[ToolSpecV2],
        request_context: RequestContextV2,
        recent_messages: list[SessionMessage],
        tool_history: list[dict[str, object]],
        last_task_digest: dict[str, object] | None,
        session_id: str = "",
    ) -> str:
        from v2.runtime.context import build_context_window, build_summary_prefix

        tool_catalog = [ChatFirstPlanner._compact_tool_summary(tool) for tool in visible_tools]
        context_messages = build_context_window(
            recent_messages,
            max_messages=16,
            max_chars_per_message=220,
            max_context_tokens=24576,
        )
        history_window = [
            {"role": item.role, "content": item.content}
            for item in context_messages
        ]
        older_messages = recent_messages[:len(recent_messages) - 16]
        summary_prefix = build_summary_prefix(older_messages, max_summary_chars=300)
        payload = {
            "current_user_message": message,
            "request_context": ChatFirstPlanner._compact_request_context(request_context),
            "recent_messages": history_window,
            "conversation_summary": summary_prefix or None,
            "last_task_digest": ChatFirstPlanner._compact_task_digest(last_task_digest),
            "tool_history": ChatFirstPlanner._compact_tool_history(tool_history[-4:]),
            "visible_tools": tool_catalog,
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _normalize_step(
        *,
        step: AgentStepV2,
        message: str,
        request_context: RequestContextV2,
        visible_tools: list[ToolSpecV2],
    ) -> AgentStepV2:
        if step.tool_calls is None:
            step.tool_calls = []

        visible_tool_names = {tool.name for tool in visible_tools}
        if step.action == "fail":
            fallback_step = ChatFirstPlanner._fallback_step_for_tool_intent(
                message=message,
                request_context=request_context,
                visible_tool_names=visible_tool_names,
            )
            if fallback_step is not None:
                return fallback_step
        if step.action != "call_tools":
            step.tool_calls = []
            return step

        if not step.tool_calls:
            fallback_step = ChatFirstPlanner._fallback_step_for_tool_intent(
                message=message,
                request_context=request_context,
                visible_tool_names=visible_tool_names,
            )
            if fallback_step is not None:
                return fallback_step
            return step

        normalized_calls: list[AgentToolCallV2] = []
        for tool_call in step.tool_calls:
            normalized_tool_name = ChatFirstPlanner._normalize_tool_name(
                tool_name=tool_call.tool_name,
                message=message,
                request_context=request_context,
                visible_tool_names=visible_tool_names,
            )
            normalized_calls.append(
                AgentToolCallV2(
                    call_id=tool_call.call_id,
                    tool_name=normalized_tool_name,
                    tool_input=ChatFirstPlanner._normalize_tool_input(
                        tool_name=normalized_tool_name,
                        tool_input=tool_call.tool_input,
                        message=message,
                        request_context=request_context,
                    ),
                )
            )
        step.tool_calls = normalized_calls
        return step

    @staticmethod
    def _normalize_tool_input(
        *,
        tool_name: str,
        tool_input: dict[str, object],
        message: str,
        request_context: RequestContextV2,
    ) -> dict[str, object]:
        payload = dict(tool_input)
        effective_task_type = request_context.task_type or detect_task_type_from_text(
            message,
            default="crop_health_detection",
        )
        effective_region = request_context.region or detect_region_from_text(message)
        effective_crop_type = request_context.crop_type or detect_crop_type_from_text(message)
        if effective_task_type == "baldness_detection":
            effective_region = effective_region or "scalp"
            effective_crop_type = effective_crop_type or "hair"
        if "query" not in payload and tool_name not in {"workspace.read_file"}:
            payload["query"] = message
        if tool_name.startswith("ktp.") or tool_name == "knowledge.search_local":
            payload = ChatFirstPlanner._merge_missing_tool_input_value(
                payload=payload,
                key="region",
                fallback=effective_region,
            )
            payload = ChatFirstPlanner._merge_missing_tool_input_value(
                payload=payload,
                key="crop_type",
                fallback=effective_crop_type,
            )
            payload = ChatFirstPlanner._merge_missing_tool_input_value(
                payload=payload,
                key="task_type",
                fallback=effective_task_type,
            )
            payload = ChatFirstPlanner._merge_missing_tool_input_value(
                payload=payload,
                key="image_path",
                fallback=request_context.image_path or extract_image_path_from_text(message),
            )
            payload = ChatFirstPlanner._merge_missing_tool_input_value(
                payload=payload,
                key="use_mock_backend",
                fallback=request_context.use_mock if request_context.use_mock is not None else False,
            )
            payload.setdefault("extra_params", dict(request_context.extra_params))
            if tool_name in {"knowledge.search_local", "ktp.explain_knowledge", "ktp.retrieve_knowledge", "ktp.analysis_pipeline"}:
                payload.setdefault("top_k", int(request_context.extra_params.get("top_k", 3) or 3))
        if tool_name == "ktp.analysis_pipeline":
            payload.setdefault("include_knowledge", bool(payload.get("include_knowledge", False)))
            payload.setdefault("include_visualization", bool(payload.get("include_visualization", False)))
        if tool_name == "workspace.read_file":
            if "path" not in payload:
                extracted_path = extract_image_path_from_text(message)
                if extracted_path:
                    payload["path"] = extracted_path
        if tool_name == "workspace.search":
            payload.setdefault("path", ".")
            payload.setdefault("limit", 8)
        return {key: value for key, value in payload.items() if value is not None}

    @staticmethod
    def _merge_missing_tool_input_value(
        *,
        payload: dict[str, object],
        key: str,
        fallback: object,
    ) -> dict[str, object]:
        current = payload.get(key)
        if current is None:
            if fallback is not None:
                payload[key] = fallback
            return payload
        if isinstance(current, str) and not current.strip():
            if fallback is not None:
                payload[key] = fallback
            else:
                payload.pop(key, None)
        return payload

    @staticmethod
    def _normalize_tool_name(
        *,
        tool_name: str,
        message: str,
        request_context: RequestContextV2,
        visible_tool_names: set[str],
    ) -> str:
        normalized = tool_name.strip()
        if normalized in visible_tool_names:
            return normalized

        alias_map = {
            "ktp.retrieve_knowledge": "ktp.retrieve_knowledge",
            "ktp.run_analysis": "ktp.analysis_pipeline",
            "knowledge.retrieve": "knowledge.search_local",
            "knowledge.search": "knowledge.search_local",
            "workspace.read": "workspace.read_file",
            "workspace.search_workspace": "workspace.search",
        }
        alias = alias_map.get(normalized)
        if alias in visible_tool_names:
            return alias

        fallback_step = ChatFirstPlanner._fallback_step_for_tool_intent(
            message=message,
            request_context=request_context,
            visible_tool_names=visible_tool_names,
        )
        if fallback_step is not None and fallback_step.tool_calls:
            return fallback_step.tool_calls[0].tool_name
        return normalized

    @staticmethod
    def _fallback_step_for_tool_intent(
        *,
        message: str,
        request_context: RequestContextV2,
        visible_tool_names: set[str],
    ) -> AgentStepV2 | None:
        preferred_tool_name = ChatFirstPlanner._infer_preferred_tool_name(
            message=message,
            request_context=request_context,
            visible_tool_names=visible_tool_names,
        )
        if preferred_tool_name is None:
            return None
        return AgentStepV2(
            action="call_tools",
            reasoning="Recovered a visible tool call from the detected user intent after normalizing the planner output.",
            tool_calls=[AgentToolCallV2(tool_name=preferred_tool_name, tool_input={})],
        )

    @staticmethod
    def _infer_preferred_tool_name(
        *,
        message: str,
        request_context: RequestContextV2,
        visible_tool_names: set[str],
    ) -> str | None:
        lowered = message.lower()
        if any(
            keyword in lowered
            for keyword in ("apsim", "作物模拟", "作物生长", "crop simulation", "crop model")
        ) and "apsim.crop_simulation" in visible_tool_names:
            return "apsim.crop_simulation"
        if any(keyword in lowered for keyword in ("训练", "train")) and "ktp.trigger_training" in visible_tool_names:
            return "ktp.trigger_training"
        return None

    @staticmethod
    def _compact_tool_summary(tool: ToolSpecV2) -> dict[str, object]:
        schema_keys = []
        if isinstance(tool.input_schema, dict):
            schema_keys = sorted(str(key) for key in tool.input_schema.keys())[:6]
        return {
            "name": tool.name,
            "category": tool.category,
            "hint": tool.usage_hint or tool.description[:96],
            "inputs": schema_keys,
            "dangerous": tool.user_confirmation_required,
            "macro": tool.is_macro,
        }

    @staticmethod
    def _compact_request_context(request_context: RequestContextV2) -> dict[str, object]:
        payload = {
            "entrypoint": request_context.entrypoint,
            "conversation_mode": request_context.conversation_mode,
            "region": request_context.region,
            "crop_type": request_context.crop_type,
            "task_type": request_context.task_type,
            "image_path": request_context.image_path,
        }
        if request_context.attachments:
            payload["attachments"] = [attachment.path for attachment in request_context.attachments[:2]]
        if request_context.extra_params:
            payload["extra_params"] = {
                str(key): value
                for key, value in list(request_context.extra_params.items())[:6]
                if value is not None
            }
        return {key: value for key, value in payload.items() if value not in (None, [], {})}

    @staticmethod
    def _compact_task_digest(last_task_digest: dict[str, object] | None) -> dict[str, object] | None:
        if not isinstance(last_task_digest, dict):
            return None
        compact: dict[str, object] = {}
        for key in ("tool_name", "summary", "status", "report_title", "visualization_title", "confidence_label"):
            value = last_task_digest.get(key)
            if value:
                compact[key] = ChatFirstPlanner._trim_text(str(value), limit=160)
        return compact or None

    @staticmethod
    def _compact_tool_history(tool_history: list[dict[str, object]]) -> list[dict[str, object]]:
        compact_history: list[dict[str, object]] = []
        for item in tool_history:
            compact_item = {
                "tool_name": item.get("tool_name"),
                "status": item.get("status"),
                "summary": ChatFirstPlanner._trim_text(str(item.get("summary", "")), limit=120),
            }
            compact_history.append({key: value for key, value in compact_item.items() if value})
        return compact_history

    @staticmethod
    def _trim_text(text: str, *, limit: int) -> str:
        compact = " ".join(text.strip().split())
        if len(compact) <= limit:
            return compact
        return compact[: limit - 3] + "..."


def format_recent_messages(messages: Iterable[SessionMessage]) -> list[dict[str, str]]:
    return [{"role": item.role, "content": item.content} for item in messages]
