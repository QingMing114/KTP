from __future__ import annotations

import json
from typing import Any


class IntegrationChatFirstLLMProvider:
    """Deterministic chat-first LLM stub used by integration and e2e tests."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.last_call_metadata: dict[str, Any] = {}
        self._call_counter = 0

    def generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int | None = None,
    ) -> str:
        self.last_call_metadata = {}
        self.calls.append(
            {
                "kind": "text",
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "max_tokens": max_tokens,
            }
        )
        prompt = user_prompt.lower()
        if "claude" in prompt and "gpt" in prompt:
            return "Claude 和 GPT 都是通用大模型产品，但侧重点、交互风格和工具集成方式并不完全相同。"
        if "claude" in prompt:
            return "Claude 是 Anthropic 推出的通用大模型与对话产品系列。"
        if "gpt" in prompt:
            return "GPT 通常指 OpenAI 的生成式预训练模型家族，也常代指其聊天产品形态。"
        return "我是一个可聊天、可调用工具、也能执行 KTP 分析流程的智能体。"

    def generate_structured(self, *, system_prompt: str, user_prompt: str, response_model):
        del system_prompt
        self.last_call_metadata = {}
        self.calls.append({"kind": "structured", "user_prompt": user_prompt})
        payload = self._parse_payload(user_prompt)
        message = str(payload.get("current_user_message", ""))
        request_context = payload.get("request_context", {})
        tool_history = payload.get("tool_history", [])

        if tool_history:
            return response_model.model_validate(
                {
                    "action": "reply",
                    "reasoning": "The requested tool run has completed, so return a concise user-facing summary.",
                    "response_message": self._build_followup_reply(
                        message=message,
                        request_context=request_context,
                        tool_history=tool_history,
                    ),
                }
            )

        if self._should_use_analysis(message=message, request_context=request_context):
            tool_input: dict[str, Any] = {}
            if request_context.get("entrypoint") == "detect":
                tool_input["include_knowledge"] = True
                tool_input["include_visualization"] = True
            elif self._mentions_visualization(message):
                tool_input["include_visualization"] = True
            return response_model.model_validate(
                {
                    "action": "call_tools",
                    "reasoning": "This request is a task-oriented KTP analysis and should run through the macro pipeline.",
                    "tool_calls": [
                        {
                            "call_id": self._next_call_id(),
                            "tool_name": "ktp.analysis_pipeline",
                            "tool_input": tool_input,
                        }
                    ],
                }
            )

        if self._should_use_knowledge(message=message, request_context=request_context):
            return response_model.model_validate(
                {
                    "action": "call_tools",
                    "reasoning": "This request asks for grounded domain knowledge and should retrieve local sources first.",
                    "tool_calls": [
                        {
                            "call_id": self._next_call_id(),
                            "tool_name": "knowledge.search_local",
                            "tool_input": {},
                        }
                    ],
                }
            )

        return response_model.model_validate(
            {
                "action": "reply",
                "reasoning": "This is normal chat and can be answered directly.",
                "response_message": self.generate_text(
                    system_prompt="",
                    user_prompt=message,
                    max_tokens=None,
                ),
            }
        )

    def _next_call_id(self) -> str:
        self._call_counter += 1
        return f"stub-tool-{self._call_counter}"

    @staticmethod
    def _parse_payload(user_prompt: str) -> dict[str, Any]:
        try:
            payload = json.loads(user_prompt)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _mentions_visualization(message: str) -> bool:
        lowered = message.lower()
        markers = ("可视化", "visualization", "visualise", "visualize")
        return any(marker in lowered for marker in markers)

    @staticmethod
    def _should_use_analysis(*, message: str, request_context: dict[str, Any]) -> bool:
        if request_context.get("conversation_mode") == "task":
            return True
        lowered = message.lower()
        analysis_markers = (
            "分析",
            "检测",
            "报告",
            "置信度",
            "可视化",
            "长势",
            "估产",
            "workflow",
            "report",
            "confidence",
            "visualization",
            "visualize",
            "assess",
            "analyze",
            ".tif",
            ".tiff",
            "/data/",
        )
        return any(marker in lowered for marker in analysis_markers)

    @staticmethod
    def _should_use_knowledge(*, message: str, request_context: dict[str, Any]) -> bool:
        if request_context.get("conversation_mode") == "task":
            return False
        lowered = message.lower()
        knowledge_markers = (
            "知识",
            "资料",
            "来源",
            "source",
            "引用",
            "解释",
            "区别",
            "干旱",
            "病害",
            "监测",
            "小麦",
            "玉米",
            "水稻",
            "ndvi",
            "evi",
            "henan",
            "wheat",
        )
        return any(marker in lowered for marker in knowledge_markers)

    @staticmethod
    def _build_followup_reply(
        *,
        message: str,
        request_context: dict[str, Any],
        tool_history: list[dict[str, Any]],
    ) -> str:
        last_tool = str(tool_history[-1].get("tool_name", "")) if tool_history else ""
        if last_tool == "knowledge.search_local":
            return "根据本地知识库，河南小麦监测常见风险包括干旱胁迫、病害压力和田间管理波动；相关资料来源已经一并附上。"
        if last_tool == "ktp.analysis_pipeline":
            include_visualization = request_context.get("entrypoint") == "detect" or IntegrationChatFirstLLMProvider._mentions_visualization(message)
            if include_visualization:
                return "KTP 分析已完成，报告、置信度和可视化结果都已经生成。"
            return "KTP 分析已完成，报告和置信度结果已经生成。"
        return "处理已经完成，结果已整理好。"
