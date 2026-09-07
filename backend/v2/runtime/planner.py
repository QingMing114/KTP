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
from schemas.runtime import AgentStepV2, AgentToolCallV2, RequestContextV2, SessionMessage, ToolSpecV2


class ChatFirstPlanner:
    """Structured chat-first planner that delegates step selection to the shared LLM."""

    def __init__(self, *, llm_provider: AgentLLMProvider | None, system_prompt_suffix: str = "") -> None:
        self._llm_provider = llm_provider
        self._system_prompt_suffix = system_prompt_suffix

    def plan(
        self,
        *,
        message: str,
        visible_tools: list[ToolSpecV2],
        request_context: RequestContextV2,
        recent_messages: list[SessionMessage],
        tool_history: list[dict[str, object]],
        last_task_digest: dict[str, object] | None,
        memory_context: str = "",
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
                memory_context=memory_context,
            ),
            response_model=AgentStepV2,
        )
        return self._normalize_step(
            step=step,
            message=message,
            request_context=request_context,
            visible_tools=visible_tools,
            tool_history=tool_history,
        )

    def _build_system_prompt(self, *, request_context: RequestContextV2) -> str:
        task_mode_rules = (
            "conversation_mode=task: 用户有明确的任务需求，优先选择最匹配的工具执行，不要选无关工具。"
            if request_context.conversation_mode == "task"
            else "conversation_mode=chat: 优先直接回答，确实需要外部能力时才调用工具。"
        )
        return (
            "你是 KTP Chat-First Agent 的 planner。"
            "严格输出一个符合 AgentStepV2 的 JSON 对象。"
            "action 只能是 reply、clarify、call_tools、delegate、fail。"
            "【delegate 说明】将物理计算任务委派给专用执行智能体（executor_30b）："
            "当用户需要运行 PROSAIL LAI 反演（prosail.lai_html_report）、"
            "APSIM 产量模拟（apsim.*）等物理模型计算时使用 delegate，"
            "委派时需设置 delegation_target='executor_30b'、delegation_goal='<具体任务描述>'。"
            "对话、文档检索等非物理计算任务不要使用 delegate。"
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
            "prosail.lai_html_report — TIF影像LAI反演并生成交互报告（像元级进度+场景参数搜索空间推理+BLAS加速），提供TIF做LAI分析时的首选"
            "prosail.invert_lai — 单像素LAI反演"
            "prosail.invert_lai_tif — 批量LAI反演仅输出tif（用户明确不要报告时用）"
            "apsim.crop_simulation — APSIM作物生长模拟"
            "workspace.search / workspace.read_file / workspace.write — 工作区文件操作"
            "【选择原则】"
            "1. 用户需要端到端分析 → ktp.analysis_pipeline"
            "2. 用户只需要某个步骤 → 选对应子工具"
            "3. 用户明确指定工具 → 按用户要求选择"
            "4. 用户提供TIF影像并要LAI反演 → prosail.lai_html_report（默认，含像元进度/场景参数推理/BLAS加速/交互报告）"
            "5. 用户明确只要TIF输出或LAI数值、不要报告 → prosail.invert_lai_tif（tif）或 prosail.invert_lai（单像素）"
            "6. 用户需要作物模拟 → apsim.crop_simulation"
            "7. 不要因为提到领域词就盲目调工具"
            "reply/clarify/fail 要写 response_message。call_tools 要写 tool_calls。"
            "默认使用用户语言，简洁自然。"
            "【防循环】tool_history 中已有相同工具成功结果时必须 reply，绝不重复调用。"
            f"{task_mode_rules}"
            f"{self._system_prompt_suffix}"
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
        memory_context: str = "",
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
            "retrieved_memory": memory_context or None,
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
        tool_history: list[dict[str, object]] | None = None,
    ) -> AgentStepV2:
        if step.tool_calls is None:
            step.tool_calls = []

        visible_tool_names = {tool.name for tool in visible_tools}

        if step.action == "call_tools" and step.tool_calls and tool_history:
            import json as _json
            successful_tool_signatures = set()
            for item in tool_history:
                if item.get("status") == "success":
                    tool_name = item.get("tool_name", "")
                    tool_input = item.get("tool_input", {})
                    try:
                        input_hash = _json.dumps(tool_input, sort_keys=True)
                    except (TypeError, ValueError):
                        input_hash = str(tool_input)
                    successful_tool_signatures.add((tool_name, input_hash))
            duplicate_calls = []
            for tc in step.tool_calls:
                try:
                    tc_input_hash = _json.dumps(tc.tool_input, sort_keys=True)
                except (TypeError, ValueError):
                    tc_input_hash = str(tc.tool_input)
                if (tc.tool_name, tc_input_hash) in successful_tool_signatures:
                    duplicate_calls.append(tc)
            if duplicate_calls:
                last_summary = ""
                for item in reversed(tool_history):
                    if item.get("tool_name") == duplicate_calls[0].tool_name and item.get("status") == "success":
                        last_summary = str(item.get("summary", ""))[:300]
                        break
                return AgentStepV2(
                    action="reply",
                    reasoning=f"工具 {duplicate_calls[0].tool_name} 已成功执行，直接回复结果，避免重复调用。",
                    response_message=last_summary or f"工具 {duplicate_calls[0].tool_name} 已执行完成。",
                    tool_calls=[],
                )
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
        # A valid visible structured tool decision is authoritative.  Keyword
        # rules are reserved for repairing an empty/unknown decision above.
        step.tool_calls = normalized_calls
        return step

    @staticmethod
    def _correct_tool_intent(
        *,
        calls: list,
        message: str,
        visible_tool_names: set[str],
    ) -> list:
        if not calls:
            return calls
        lowered = message.lower()
        _intent_rules: list[tuple[set[str], str]] = [
            ({"apsim", "作物模拟", "作物生长", "crop simulation", "crop model", "生长过程", "生长模拟", "播种到收获", "生长周期", "生育期模拟"}, "apsim.crop_simulation"),
            ({"prosail", "光谱模拟", "spectral", "reflectance", "光谱反射率", "反射率模拟", "反射率计算", "光谱计算"}, "prosail.simulation"),
            ({"lai反演", "invert lai", "反演lai"}, "prosail.invert_lai"),
        ]
        for keywords, correct_tool in _intent_rules:
            if any(kw in lowered for kw in keywords) and correct_tool in visible_tool_names:
                for i, call in enumerate(calls):
                    if call.tool_name != correct_tool and call.tool_name in {
                        "ktp.analysis_pipeline",
                        "ktp.run_inference_workflow",
                    }:
                        calls[i] = type(call)(
                            call_id=call.call_id,
                            tool_name=correct_tool,
                            tool_input={"query": message, **{k: v for k, v in (call.tool_input or {}).items() if k != "query"}},
                        )
                break
        return calls

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
                fallback=(
                    request_context.image_path
                    or (request_context.datasets[0].local_path if request_context.datasets else None)
                    or extract_image_path_from_text(message)
                ),
            )
            payload = ChatFirstPlanner._merge_missing_tool_input_value(
                payload=payload,
                key="use_mock_backend",
                fallback=request_context.use_mock if request_context.use_mock is not None else False,
            )
            payload.setdefault("extra_params", dict(request_context.extra_params))
            if tool_name in {"knowledge.search_local", "ktp.explain_knowledge", "ktp.retrieve_knowledge", "ktp.analysis_pipeline"}:
                payload.setdefault("top_k", int(request_context.extra_params.get("top_k", 3) or 3))
        if tool_name in {"prosail.lai_html_report", "prosail.invert_lai_tif"}:
            payload = ChatFirstPlanner._merge_missing_tool_input_value(
                payload=payload,
                key="image_path",
                fallback=(
                    request_context.image_path
                    or (request_context.datasets[0].local_path if request_context.datasets else None)
                ),
            )
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
        alias_map = {
            "ktp.retrieve_knowledge": "ktp.explain_knowledge",
            "ktp.run_analysis": "ktp.analysis_pipeline",
            "knowledge.retrieve": "knowledge.search_local",
            "knowledge.search": "knowledge.search_local",
            "workspace.read": "workspace.read_file",
            "workspace.search_workspace": "workspace.search",
        }
        alias = alias_map.get(normalized)
        if alias in visible_tool_names:
            return alias

        if normalized in visible_tool_names:
            return normalized

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
            for keyword in ("apsim", "作物模拟", "作物生长", "crop simulation", "crop model", "生长过程", "生长模拟", "播种到收获", "生长周期", "生育期模拟")
        ) and "apsim.crop_simulation" in visible_tool_names:
            return "apsim.crop_simulation"
        if any(keyword in lowered for keyword in ("训练", "train")) and "ktp.trigger_training" in visible_tool_names:
            return "ktp.trigger_training"
        if any(
            keyword in lowered
            for keyword in ("prosail", "光谱模拟", "spectral simulation", "reflectance simulation", "光谱反射率", "反射率模拟", "反射率计算", "光谱计算")
        ) and "prosail.simulation" in visible_tool_names:
            return "prosail.simulation"
        if any(
            keyword in lowered
            for keyword in ("lai反演", "invert lai", "反演lai", "lai inversion", "反演lai值", "反演 lai")
        ) and "prosail.invert_lai" in visible_tool_names:
            tif_image_path = request_context.image_path or extract_image_path_from_text(message)
            if tif_image_path:
                tif_suffix = tif_image_path.lower()
                if tif_suffix.endswith(('.tif', '.tiff')) or any(keyword in lowered for keyword in ("tif", "geotiff", "geospatial", "影像", "多光谱", "multispectral")):
                    # TIF + LAI 反演默认走富功能报告工具：像元级进度、PROSAIL 场景参数搜索空间推理、
                    # BLAS 向量化加速、交互式 HTML 报告。仅当用户明确只要 TIF/数值、不要报告时退回裸工具。
                    wants_bare = any(
                        k in lowered
                        for k in ("不要报告", "无需报告", "不用报告", "只要tif", "只要 tif", "仅tif", "只输出tif", "只要数值", "只要lai值", "只需数值")
                    )
                    if not wants_bare and "prosail.lai_html_report" in visible_tool_names:
                        return "prosail.lai_html_report"
                    if "prosail.invert_lai_tif" in visible_tool_names:
                        return "prosail.invert_lai_tif"
            return "prosail.invert_lai"
        if any(
            keyword in lowered
            for keyword in ("写入文件", "写文件", "write file", "保存文件")
        ) and "workspace.write" in visible_tool_names:
            return "workspace.write"
        if any(
            keyword in lowered
            for keyword in ("读取文件", "读文件", "read file", "查看文件内容")
        ) and "workspace.read_file" in visible_tool_names:
            return "workspace.read_file"
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
        if request_context.datasets:
            payload["datasets"] = [
                {
                    "dataset_id": dataset.dataset_id,
                    "display_name": dataset.display_name,
                    "region": dataset.region,
                    "crop_type": dataset.crop_type,
                    "task_type": dataset.task_type,
                }
                for dataset in request_context.datasets[:4]
            ]
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
