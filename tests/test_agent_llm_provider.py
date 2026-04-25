"""Unit tests for shared planner/executor LLM helpers."""

from __future__ import annotations

import httpx
import pytest
from pydantic import BaseModel

from infra.llm.config import AgentLLMConfig
from infra.llm.provider import (
    AgentLLMError,
    OpenAICompatibleProvider,
    _extract_json_object,
    _build_response_contract,
    _build_structured_prompt,
    _parse_worker_startup_payload,
)
from shared.schemas.executor import ExecutorTaskOutput
from shared.schemas.planner import PlannerResult
from v2.shared.schemas import AgentStepV2


def test_build_response_contract_compacts_types() -> None:
    contract = _build_response_contract(PlannerResult)

    assert contract == {
        "crop_type": "string|null",
        "need_confidence": "boolean",
        "need_rag": "boolean",
        "need_report": "boolean",
        "need_training": "boolean",
        "reasoning_summary": "string",
        "region": "string|null",
        "task_type": "string",
    }


def test_build_structured_prompt_uses_compact_contract() -> None:
    prompt = _build_structured_prompt(
        user_prompt="Summarize this tool result.",
        response_model=ExecutorTaskOutput,
    )

    assert "Return exactly one valid JSON object." in prompt
    assert "Do not wrap it in markdown" in prompt
    assert "\"success\": \"boolean\"" in prompt
    assert "\"output\": \"object\"" in prompt
    assert "\"message\": \"string\"" in prompt


def test_parse_worker_startup_payload_returns_runtime() -> None:
    runtime = _parse_worker_startup_payload(
        {
            "ok": True,
            "ready": True,
            "runtime": {"accelerator": "cuda", "dtype": "auto"},
        }
    )

    assert runtime == {"accelerator": "cuda", "dtype": "auto"}


def test_parse_worker_startup_payload_rejects_unready_payload() -> None:
    with pytest.raises(AgentLLMError):
        _parse_worker_startup_payload(
            {
                "ok": True,
                "ready": False,
                "runtime": {},
            }
        )


def test_extract_json_object_salvages_incomplete_direct_answer_payload() -> None:
    payload = _extract_json_object(
        '{"action":"direct_answer","reason":"general_knowledge","answer":"NDVI 和 EVI 都是植被指数，但 EVI 在高覆盖区通常更稳健'
    )

    assert payload["action"] == "direct_answer"
    assert payload["reason"] == "general_knowledge"
    assert "EVI" in payload["answer"]


def test_openai_provider_retries_transient_503_and_returns_text(monkeypatch: pytest.MonkeyPatch) -> None:
    config = AgentLLMConfig()
    config.backend = "openai_compatible"
    config.openai_api_base = "http://example.test/v1"
    config.openai_model_name = "demo-model"
    config.openai_max_retries = 2
    config.openai_retry_backoff_seconds = 0.0
    provider = OpenAICompatibleProvider(config)
    request = httpx.Request("POST", "http://example.test/v1/chat/completions")
    responses = [
        httpx.Response(503, request=request, text="engine warming up"),
        httpx.Response(
            200,
            request=request,
            json={"choices": [{"message": {"reasoning": "", "content": "Claude 是 Anthropic 的模型系列。"}}]},
        ),
    ]

    class FakeClient:
        def post(self, path: str, json: dict[str, object]) -> httpx.Response:
            assert path == "/chat/completions"
            assert json["model"] == "demo-model"
            return responses.pop(0)

    monkeypatch.setattr(provider, "_client", FakeClient())

    text = provider.generate_text(system_prompt="system", user_prompt="user")

    assert text == "Claude 是 Anthropic 的模型系列。"


def test_openai_provider_reports_retry_count_and_response_body(monkeypatch: pytest.MonkeyPatch) -> None:
    config = AgentLLMConfig()
    config.backend = "openai_compatible"
    config.openai_api_base = "http://example.test/v1"
    config.openai_model_name = "demo-model"
    config.openai_max_retries = 1
    config.openai_retry_backoff_seconds = 0.0
    provider = OpenAICompatibleProvider(config)
    request = httpx.Request("POST", "http://example.test/v1/chat/completions")
    responses = [
        httpx.Response(503, request=request, text="temporarily unavailable"),
        httpx.Response(503, request=request, text="queue full"),
    ]

    class FakeClient:
        def post(self, path: str, json: dict[str, object]) -> httpx.Response:
            assert path == "/chat/completions"
            return responses.pop(0)

    monkeypatch.setattr(provider, "_client", FakeClient())

    with pytest.raises(AgentLLMError) as exc_info:
        provider.generate_text(system_prompt="system", user_prompt="user")

    assert "after 2 attempt(s)" in str(exc_info.value)
    assert "queue full" in str(exc_info.value)
    assert exc_info.value.category == "upstream_overloaded"
    assert exc_info.value.status_code == 503


def test_openai_provider_uses_smaller_budget_for_structured_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MiniStructuredResponse(BaseModel):
        success: bool
        output: dict[str, object]
        message: str

    config = AgentLLMConfig()
    config.backend = "openai_compatible"
    config.openai_api_base = "http://example.test/v1"
    config.openai_model_name = "demo-model"
    config.max_new_tokens = 2048
    config.structured_max_new_tokens = 320
    provider = OpenAICompatibleProvider(config)
    recorded_max_tokens: list[int] = []
    request = httpx.Request("POST", "http://example.test/v1/chat/completions")

    class FakeClient:
        def post(self, path: str, json: dict[str, object]) -> httpx.Response:
            assert path == "/chat/completions"
            recorded_max_tokens.append(int(json["max_tokens"]))
            if len(recorded_max_tokens) == 1:
                return httpx.Response(
                    200,
                    request=request,
                    json={"choices": [{"message": {"reasoning": "", "content": '{"success":true,"output":{},"message":"ok"}'}}]},
                )
            return httpx.Response(
                200,
                request=request,
                json={"choices": [{"message": {"reasoning": "", "content": "plain text"}}]},
            )

    monkeypatch.setattr(provider, "_client", FakeClient())

    result = provider.generate_structured(
        system_prompt="system",
        user_prompt="user",
        response_model=MiniStructuredResponse,
    )
    text = provider.generate_text(system_prompt="system", user_prompt="user")

    assert result.success is True
    assert text == "plain text"
    assert recorded_max_tokens == [320, 2048]


def test_openai_provider_retries_structured_calls_when_output_is_truncated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = AgentLLMConfig()
    config.backend = "openai_compatible"
    config.openai_api_base = "http://example.test/v1"
    config.openai_model_name = "demo-model"
    config.max_new_tokens = 2048
    config.structured_max_new_tokens = 320
    provider = OpenAICompatibleProvider(config)
    recorded_max_tokens: list[int] = []
    request = httpx.Request("POST", "http://example.test/v1/chat/completions")

    class FakeClient:
        def post(self, path: str, json: dict[str, object]) -> httpx.Response:
            assert path == "/chat/completions"
            recorded_max_tokens.append(int(json["max_tokens"]))
            if len(recorded_max_tokens) == 1:
                return httpx.Response(
                    200,
                    request=request,
                    json={
                        "choices": [
                            {
                                "finish_reason": "length",
                                "message": {
                                    "reasoning": "",
                                    "content": '{"action":"reply","reasoning":"brief","response_message":"截断"}',
                                },
                            }
                        ]
                    },
                )
            return httpx.Response(
                200,
                request=request,
                json={
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "reasoning": "",
                                "content": '{"action":"reply","reasoning":"brief","response_message":"完整回答"}',
                            },
                        }
                    ]
                },
            )

    monkeypatch.setattr(provider, "_client", FakeClient())

    step = provider.generate_structured(
        system_prompt="system",
        user_prompt="user",
        response_model=AgentStepV2,
    )

    assert step.response_message == "完整回答"
    assert recorded_max_tokens == [320, 768]


def test_openai_provider_disables_qwen3_thinking_in_request_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = AgentLLMConfig()
    config.backend = "openai_compatible"
    config.openai_api_base = "http://example.test/v1"
    config.openai_model_name = "/models/Qwen/Qwen3.5-27B"
    provider = OpenAICompatibleProvider(config)
    request = httpx.Request("POST", "http://example.test/v1/chat/completions")
    recorded_payloads: list[dict[str, object]] = []

    class FakeClient:
        def post(self, path: str, json: dict[str, object]) -> httpx.Response:
            assert path == "/chat/completions"
            recorded_payloads.append(json)
            return httpx.Response(
                200,
                request=request,
                json={"choices": [{"message": {"reasoning": "", "content": "plain text"}}]},
            )

    monkeypatch.setattr(provider, "_client", FakeClient())

    text = provider.generate_text(system_prompt="system", user_prompt="user")

    assert text == "plain text"
    assert recorded_payloads[0]["chat_template_kwargs"] == {"enable_thinking": False}


def test_openai_provider_marks_reasoning_only_reply_as_incomplete_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = AgentLLMConfig()
    config.backend = "openai_compatible"
    config.openai_api_base = "http://example.test/v1"
    config.openai_model_name = "demo-model"
    config.openai_max_retries = 0
    provider = OpenAICompatibleProvider(config)
    request = httpx.Request("POST", "http://example.test/v1/chat/completions")

    class FakeClient:
        def post(self, path: str, json: dict[str, object]) -> httpx.Response:
            assert path == "/chat/completions"
            return httpx.Response(
                200,
                request=request,
                json={"choices": [{"message": {"reasoning": "internal chain of thought", "content": None}}]},
            )

    monkeypatch.setattr(provider, "_client", FakeClient())

    with pytest.raises(AgentLLMError) as exc_info:
        provider.generate_text(system_prompt="system", user_prompt="user", max_tokens=256)

    assert exc_info.value.category == "incomplete_generation"
    assert exc_info.value.request_kind == "direct_reply"


def test_openai_provider_marks_length_finish_reason_as_incomplete_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = AgentLLMConfig()
    config.backend = "openai_compatible"
    config.openai_api_base = "http://example.test/v1"
    config.openai_model_name = "demo-model"
    config.openai_max_retries = 0
    provider = OpenAICompatibleProvider(config)
    request = httpx.Request("POST", "http://example.test/v1/chat/completions")

    class FakeClient:
        def post(self, path: str, json: dict[str, object]) -> httpx.Response:
            assert path == "/chat/completions"
            return httpx.Response(
                200,
                request=request,
                json={
                    "choices": [
                        {
                            "finish_reason": "length",
                            "message": {
                                "reasoning": "",
                                "content": "这是一段被截断的回答",
                            },
                        }
                    ]
                },
            )

    monkeypatch.setattr(provider, "_client", FakeClient())

    with pytest.raises(AgentLLMError) as exc_info:
        provider.generate_text(system_prompt="system", user_prompt="user", max_tokens=256)

    assert exc_info.value.category == "incomplete_generation"
    assert exc_info.value.request_kind == "direct_reply"


def test_openai_provider_accepts_content_alias_for_response_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MiniPlannerStep(BaseModel):
        action: str
        reasoning: str
        response_message: str | None = None

    config = AgentLLMConfig()
    config.backend = "openai_compatible"
    config.openai_api_base = "http://example.test/v1"
    config.openai_model_name = "demo-model"
    provider = OpenAICompatibleProvider(config)
    request = httpx.Request("POST", "http://example.test/v1/chat/completions")

    class FakeClient:
        def post(self, path: str, json: dict[str, object]) -> httpx.Response:
            assert path == "/chat/completions"
            return httpx.Response(
                200,
                request=request,
                json={
                    "choices": [
                        {
                            "message": {
                                "reasoning": "reply directly",
                                "content": '{"action":"reply","reasoning":"reply directly","content":"Claude 是 Anthropic 的模型系列。"}',
                            }
                        }
                    ]
                },
            )

    monkeypatch.setattr(provider, "_client", FakeClient())

    step = provider.generate_structured(
        system_prompt="system",
        user_prompt="user",
        response_model=MiniPlannerStep,
    )

    assert step.response_message == "Claude 是 Anthropic 的模型系列。"
    assert provider.last_call_metadata["schema_alias_applied"] is True


def test_openai_provider_normalizes_tool_call_name_alias_and_inline_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = AgentLLMConfig()
    config.backend = "openai_compatible"
    config.openai_api_base = "http://example.test/v1"
    config.openai_model_name = "demo-model"
    provider = OpenAICompatibleProvider(config)
    request = httpx.Request("POST", "http://example.test/v1/chat/completions")

    class FakeClient:
        def post(self, path: str, json: dict[str, object]) -> httpx.Response:
            assert path == "/chat/completions"
            return httpx.Response(
                200,
                request=request,
                json={
                    "choices": [
                        {
                            "message": {
                                "reasoning": "use grounded knowledge",
                                "content": (
                                    '{"action":"call_tools","reasoning":"need sources",'
                                    '"tool_calls":[{"name":"ktp.explain_knowledge",'
                                    '"query":"请解释 NDVI 和 EVI 的区别","top_k":5}]}'
                                ),
                            }
                        }
                    ]
                },
            )

    monkeypatch.setattr(provider, "_client", FakeClient())

    step = provider.generate_structured(
        system_prompt="system",
        user_prompt="user",
        response_model=AgentStepV2,
    )

    assert step.tool_calls[0].tool_name == "ktp.explain_knowledge"
    assert step.tool_calls[0].tool_input == {
        "query": "请解释 NDVI 和 EVI 的区别",
        "top_k": 5,
    }
    assert provider.last_call_metadata["schema_alias_applied"] is True


def test_openai_provider_accepts_reason_alias_for_reasoning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = AgentLLMConfig()
    config.backend = "openai_compatible"
    config.openai_api_base = "http://example.test/v1"
    config.openai_model_name = "demo-model"
    provider = OpenAICompatibleProvider(config)
    request = httpx.Request("POST", "http://example.test/v1/chat/completions")

    class FakeClient:
        def post(self, path: str, json: dict[str, object]) -> httpx.Response:
            assert path == "/chat/completions"
            return httpx.Response(
                200,
                request=request,
                json={
                    "choices": [
                        {
                            "message": {
                                "reasoning": "use alias-compatible structured response",
                                "content": (
                                    '{"action":"reply","reason":"grounded answer",'
                                    '"response_message":"这里是整理后的回答。"}'
                                ),
                            }
                        }
                    ]
                },
            )

    monkeypatch.setattr(provider, "_client", FakeClient())

    step = provider.generate_structured(
        system_prompt="system",
        user_prompt="user",
        response_model=AgentStepV2,
    )

    assert step.reasoning == "grounded answer"
    assert step.response_message == "这里是整理后的回答。"
    assert provider.last_call_metadata["schema_alias_applied"] is True


def test_openai_provider_accepts_response_alias_for_response_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = AgentLLMConfig()
    config.backend = "openai_compatible"
    config.openai_api_base = "http://example.test/v1"
    config.openai_model_name = "demo-model"
    provider = OpenAICompatibleProvider(config)
    request = httpx.Request("POST", "http://example.test/v1/chat/completions")

    class FakeClient:
        def post(self, path: str, json: dict[str, object]) -> httpx.Response:
            assert path == "/chat/completions"
            return httpx.Response(
                200,
                request=request,
                json={
                    "choices": [
                        {
                            "message": {
                                "reasoning": "use alias-compatible structured response",
                                "content": (
                                    '{"action":"reply","reasoning":"brief summary",'
                                    '"response":"未检索到可靠资料来源，建议补充知识库后再查询。"}'
                                ),
                            }
                        }
                    ]
                },
            )

    monkeypatch.setattr(provider, "_client", FakeClient())

    step = provider.generate_structured(
        system_prompt="system",
        user_prompt="user",
        response_model=AgentStepV2,
    )

    assert step.reasoning == "brief summary"
    assert step.response_message == "未检索到可靠资料来源，建议补充知识库后再查询。"
    assert provider.last_call_metadata["schema_alias_applied"] is True


def test_openai_provider_accepts_null_tool_calls_for_reply_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = AgentLLMConfig()
    config.backend = "openai_compatible"
    config.openai_api_base = "http://example.test/v1"
    config.openai_model_name = "demo-model"
    provider = OpenAICompatibleProvider(config)
    request = httpx.Request("POST", "http://example.test/v1/chat/completions")

    class FakeClient:
        def post(self, path: str, json: dict[str, object]) -> httpx.Response:
            assert path == "/chat/completions"
            return httpx.Response(
                200,
                request=request,
                json={
                    "choices": [
                        {
                            "message": {
                                "reasoning": "use alias-compatible structured response",
                                "content": (
                                    '{"action":"reply","reasoning":"summarize the result",'
                                    '"response_message":"分析已完成。","tool_calls":null}'
                                ),
                            }
                        }
                    ]
                },
            )

    monkeypatch.setattr(provider, "_client", FakeClient())

    step = provider.generate_structured(
        system_prompt="system",
        user_prompt="user",
        response_model=AgentStepV2,
    )

    assert step.action == "reply"
    assert step.response_message == "分析已完成。"
    assert step.tool_calls == []
    assert provider.last_call_metadata["schema_alias_applied"] is True


def test_openai_provider_accepts_top_level_tool_call_alias_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = AgentLLMConfig()
    config.backend = "openai_compatible"
    config.openai_api_base = "http://example.test/v1"
    config.openai_model_name = "demo-model"
    provider = OpenAICompatibleProvider(config)
    request = httpx.Request("POST", "http://example.test/v1/chat/completions")

    class FakeClient:
        def post(self, path: str, json: dict[str, object]) -> httpx.Response:
            assert path == "/chat/completions"
            return httpx.Response(
                200,
                request=request,
                json={
                    "choices": [
                        {
                            "message": {
                                "reasoning": "use alias-compatible structured response",
                                "content": (
                                    '{"action":"call_tool","reasoning":"run the analysis macro",'
                                    '"tool_call":{"name":"ktp.analysis_pipeline","query":"真实斑秃识别"}}'
                                ),
                            }
                        }
                    ]
                },
            )

    monkeypatch.setattr(provider, "_client", FakeClient())

    step = provider.generate_structured(
        system_prompt="system",
        user_prompt="user",
        response_model=AgentStepV2,
    )

    assert step.tool_call is not None
    assert step.tool_call.tool_name == "ktp.analysis_pipeline"
    assert step.tool_call.tool_input == {"query": "真实斑秃识别"}
    assert step.tool_calls[0].tool_name == "ktp.analysis_pipeline"
    assert provider.last_call_metadata["schema_alias_applied"] is True


def test_openai_provider_timeout_is_classified_as_upstream_overloaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = AgentLLMConfig()
    config.backend = "openai_compatible"
    config.openai_api_base = "http://example.test/v1"
    config.openai_model_name = "demo-model"
    config.openai_max_retries = 0
    provider = OpenAICompatibleProvider(config)
    request = httpx.Request("POST", "http://example.test/v1/chat/completions")

    class FakeClient:
        def post(self, path: str, json: dict[str, object]) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

    monkeypatch.setattr(provider, "_client", FakeClient())

    with pytest.raises(AgentLLMError) as exc_info:
        provider.generate_text(system_prompt="system", user_prompt="user", max_tokens=256)

    assert exc_info.value.category == "upstream_overloaded"
    assert exc_info.value.request_kind == "direct_reply"


def test_openai_provider_uses_request_kind_specific_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = AgentLLMConfig()
    config.backend = "openai_compatible"
    config.openai_api_base = "http://example.test/v1"
    config.openai_model_name = "demo-model"
    config.request_timeout_seconds = 45.0
    config.openai_direct_timeout_seconds = 30.0
    config.openai_structured_timeout_seconds = 120.0
    provider = OpenAICompatibleProvider(config)
    request = httpx.Request("POST", "http://example.test/v1/chat/completions")
    recorded_timeouts: list[float] = []

    class FakeClient:
        def post(self, path: str, json: dict[str, object], timeout: float | None = None) -> httpx.Response:
            assert path == "/chat/completions"
            recorded_timeouts.append(float(timeout or 0))
            if len(recorded_timeouts) == 1:
                return httpx.Response(
                    200,
                    request=request,
                    json={
                        "choices": [
                            {
                                "message": {
                                    "reasoning": "plan",
                                    "content": (
                                        '{"action":"reply","reasoning":"brief summary",'
                                        '"response_message":"planner ok"}'
                                    ),
                                }
                            }
                        ]
                    },
                )
            return httpx.Response(
                200,
                request=request,
                json={"choices": [{"message": {"reasoning": "", "content": "direct ok"}}]},
            )

    monkeypatch.setattr(provider, "_client", FakeClient())

    step = provider.generate_structured(
        system_prompt="system",
        user_prompt="user",
        response_model=AgentStepV2,
    )
    text = provider.generate_text(system_prompt="system", user_prompt="user")

    assert step.response_message == "planner ok"
    assert text == "direct ok"
    assert recorded_timeouts == [120.0, 30.0]
