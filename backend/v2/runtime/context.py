from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from v2.shared.schemas import SessionMessage
    from infra.llm.provider import AgentLLMProvider

logger = logging.getLogger(__name__)

_SUMMARY_CACHE: dict[str, str] = {}


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    ascii_count = sum(1 for c in text if ord(c) < 128)
    cjk_count = len(text) - ascii_count
    return int(ascii_count / 4 + cjk_count * 1.5 + 0.5)


def trim_message_content(content: str, max_chars: int = 300) -> str:
    if not content:
        return ""
    compact = " ".join(content.strip().split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3] + "..."


def build_context_window(
    messages: list[SessionMessage],
    *,
    max_messages: int = 20,
    max_chars_per_message: int = 300,
    max_context_tokens: int = 30720,
    system_prompt_tokens: int = 0,
    tool_catalog_tokens: int = 0,
) -> list[SessionMessage]:
    if not messages:
        return []

    available_tokens = max_context_tokens - system_prompt_tokens - tool_catalog_tokens
    if available_tokens < 500:
        available_tokens = 500

    window = messages[-max_messages:]

    result: list[SessionMessage] = []
    total_tokens = 0

    for msg in reversed(window):
        trimmed = trim_message_content(msg.content, max_chars_per_message)
        msg_tokens = estimate_tokens(trimmed) + 4
        if total_tokens + msg_tokens > available_tokens:
            break
        result.append(
            type(msg)(role=msg.role, content=trimmed)
        )
        total_tokens += msg_tokens

    result.reverse()
    logger.debug(
        "context_window_built | total=%d | trimmed=%d | tokens=%d | available=%d",
        len(messages), len(result), total_tokens, available_tokens,
    )
    return result


def build_summary_prefix(
    older_messages: list[SessionMessage],
    max_summary_chars: int = 500,
) -> str:
    if not older_messages:
        return ""

    user_msgs = [m for m in older_messages if m.role == "user"]
    assistant_msgs = [m for m in older_messages if m.role == "assistant"]

    if not user_msgs and not assistant_msgs:
        return ""

    parts = ["[对话摘要]"]
    if user_msgs:
        topics = []
        for m in user_msgs[-5:]:
            topic = m.content.strip()[:80]
            if topic:
                topics.append(topic)
        if topics:
            parts.append("用户讨论了: " + "; ".join(topics))
    if assistant_msgs:
        parts.append(f"助手回复了 {len(assistant_msgs)} 条消息")

    summary = " ".join(parts)
    if len(summary) > max_summary_chars:
        summary = summary[: max_summary_chars - 3] + "..."
    return summary


def _build_conversation_text(messages: list[SessionMessage], max_chars_per_msg: int = 200) -> str:
    lines = []
    for m in messages:
        content = m.content.strip().replace("\n", " ")[:max_chars_per_msg]
        lines.append(f"[{m.role}]: {content}")
    return "\n".join(lines)


async def ai_summarize_context(
    older_messages: list[SessionMessage],
    current_user_message: str,
    llm_provider: AgentLLMProvider,
    session_id: str = "",
    max_summary_tokens: int = 512,
) -> str:
    if not older_messages:
        return ""

    cache_key = f"{session_id}:{len(older_messages)}:{older_messages[-1].content[:50]}"
    if cache_key in _SUMMARY_CACHE:
        return _SUMMARY_CACHE[cache_key]

    conversation_text = _build_conversation_text(older_messages, max_chars_per_msg=200)
    if estimate_tokens(conversation_text) < 200:
        return build_summary_prefix(older_messages)

    system_prompt = (
        "你是一个对话摘要专家。你的任务是将一段对话历史压缩为简洁的摘要，"
        "保留以下关键信息：\n"
        "1. 用户的核心需求和目标\n"
        "2. 已经做出的重要决策和结论\n"
        "3. 用户表达的偏好或约束\n"
        "4. 未解决或待处理的问题\n"
        "5. 关键的上下文信息（如文件路径、参数值、配置等）\n\n"
        "丢弃：寒暄、重复内容、已撤销的决定、无关细节。\n"
        "用中文输出，不超过3句话。"
    )

    user_prompt = (
        f"当前用户消息: {current_user_message[:200]}\n\n"
        f"之前的对话历史:\n{conversation_text}\n\n"
        "请压缩以上对话历史，保留对当前对话最重要的信息。"
    )

    try:
        summary = llm_provider.generate_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_summary_tokens,
        ).strip()
        if not summary:
            summary = build_summary_prefix(older_messages)

        _SUMMARY_CACHE[cache_key] = summary
        logger.info(
            "ai_context_summarized | session=%s | older_msgs=%d | summary_tokens=%d",
            session_id, len(older_messages), estimate_tokens(summary),
        )
        return f"[对话摘要] {summary}"
    except Exception as exc:
        logger.warning("ai_summarize_failed | error=%s | fallback_to_rule", exc)
        return build_summary_prefix(older_messages)


async def build_smart_context(
    messages: list[SessionMessage],
    current_user_message: str,
    llm_provider: AgentLLMProvider | None = None,
    *,
    session_id: str = "",
    max_messages: int = 20,
    max_chars_per_message: int = 300,
    max_context_tokens: int = 30720,
    system_prompt_tokens: int = 0,
    tool_catalog_tokens: int = 0,
) -> tuple[list[SessionMessage], str]:
    if not messages:
        return [], ""

    context_messages = build_context_window(
        messages,
        max_messages=max_messages,
        max_chars_per_message=max_chars_per_message,
        max_context_tokens=max_context_tokens,
        system_prompt_tokens=system_prompt_tokens,
        tool_catalog_tokens=tool_catalog_tokens,
    )

    older_count = len(messages) - max_messages
    if older_count <= 0:
        return context_messages, ""

    older_messages = messages[:older_count]
    if not older_messages:
        return context_messages, ""

    if llm_provider is not None and older_count > 4:
        summary = await ai_summarize_context(
            older_messages,
            current_user_message,
            llm_provider,
            session_id=session_id,
        )
    else:
        summary = build_summary_prefix(older_messages)

    return context_messages, summary
