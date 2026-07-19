from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from shared.schemas.service_results import (
    ConfidenceServiceResult,
    InferenceServiceResult,
    ModelRegistryResult,
    RagServiceResult,
    ReportServiceResult,
    TrainingTriggerResult,
    VisualizationServiceResult,
)
from v2.adapters.python_services.ktp_rag import KtpKnowledgeAdapter
from v2.adapters.python_services.ktp_services import KtpExecutionContext, KtpServiceError
from v2.apps.api.main import _encode_sse, create_app
from v2.tools.registry import build_default_tool_registry


class _FakeRagClient:
    def run_rag(
        self,
        *,
        request_id: str | None,
        user_query: str,
        task_type: str | None,
        region: str | None,
        crop_type: str | None,
        inference_result: dict | None = None,
        context: dict | None = None,
        top_k: int | None = None,
    ) -> RagServiceResult:
        del request_id, task_type, region, crop_type, inference_result, context
        return RagServiceResult(
            query=user_query,
            summary="NDVI emphasizes greenness, while EVI is more robust to canopy saturation.",
            sources=["mock://knowledge/ndvi-evi"],
            top_k=top_k or 3,
            results=[{"chunk_id": "chunk-1", "text": "demo text", "score": 0.9}],
        )


class _SequenceStructuredLLMProvider:
    def __init__(self, *steps: dict) -> None:
        self._steps = list(steps)
        self.calls: list[dict[str, str]] = []

    def generate_text(self, *, system_prompt: str, user_prompt: str, max_tokens: int | None = None) -> str:
        self.calls.append(
            {
                "kind": "text",
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "max_tokens": str(max_tokens or ""),
            }
        )
        assert self._steps, "No more stubbed LLM steps available."
        next_step = self._steps.pop(0)
        return str(next_step.get("response_message", "stubbed text reply"))

    def generate_structured(self, *, system_prompt: str, user_prompt: str, response_model):
        self.calls.append({"kind": "structured", "system_prompt": system_prompt, "user_prompt": user_prompt})
        assert self._steps, "No more stubbed LLM steps available."
        return response_model.model_validate(self._steps.pop(0))


class _HistoryAwareStructuredLLMProvider(_SequenceStructuredLLMProvider):
    def generate_text(self, *, system_prompt: str, user_prompt: str, max_tokens: int | None = None) -> str:
        if self.calls:
            assert "你知道 Claude 吗？" in user_prompt
            assert "Claude 是 Anthropic 的模型与产品家族。" in user_prompt
        return super().generate_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
        )

    def generate_structured(self, *, system_prompt: str, user_prompt: str, response_model):
        if self.calls:
            assert "你知道 Claude 吗？" in user_prompt
            assert "Claude 是 Anthropic 的模型与产品家族。" in user_prompt
        return super().generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=response_model,
        )


class _SchemaAliasStructuredLLMProvider:
    def __init__(self) -> None:
        self.last_call_metadata: dict[str, object] = {}

    def generate_text(self, *, system_prompt: str, user_prompt: str, max_tokens: int | None = None) -> str:
        raise AssertionError("Free-form generation should not be used in schema alias test.")

    def generate_structured(self, *, system_prompt: str, user_prompt: str, response_model):
        self.last_call_metadata = {"schema_alias_applied": True}
        return response_model.model_validate(
            {
                "action": "reply",
                "reasoning": "Structured alias should be surfaced in trace.",
                "response_message": "我已经通过兼容别名接受了这次结构化回复。",
            }
        )


class _UnexpectedLLMProvider:
    def generate_text(self, *, system_prompt: str, user_prompt: str, max_tokens: int | None = None) -> str:
        del system_prompt, user_prompt, max_tokens
        raise AssertionError("LLM should not be used when runtime can clarify the invalid image path upfront.")

    def generate_structured(self, *, system_prompt: str, user_prompt: str, response_model):
        del system_prompt, user_prompt, response_model
        raise AssertionError("LLM should not be used when runtime can clarify the invalid image path upfront.")


class _FakeKtpServiceBundle:
    def create_context(
        self,
        *,
        query: str,
        region: str = "henan",
        crop_type: str = "wheat",
        task_type: str = "crop_health_detection",
        request_id: str | None = None,
        use_mock_backend: bool = False,
        image_path: str | None = None,
        top_k: int = 3,
        extra_params: dict[str, object] | None = None,
    ) -> KtpExecutionContext:
        return KtpExecutionContext(
            request_id=request_id or "ktp-fake-001",
            query=query,
            region=region,
            crop_type=crop_type,
            task_type=task_type,
            use_mock_backend=use_mock_backend,
            image_path=image_path,
            top_k=top_k,
            extra_params=extra_params or {},
        )

    def ensure_model_lookup(self, context: KtpExecutionContext) -> ModelRegistryResult:
        context.model_lookup_backend = "fake"
        context.model_registry_result = ModelRegistryResult(
            model_exists=True,
            model_id=11,
            model_name="fake-ktp-model",
            model_version="1.2.3",
            artifact_uri="mock://models/fake-ktp-model/1.2.3",
            status="ready",
        )
        return context.model_registry_result

    def ensure_inference(self, context: KtpExecutionContext) -> InferenceServiceResult:
        self.ensure_model_lookup(context)
        context.inference_backend = "fake"
        context.inference_result = InferenceServiceResult(
            mask_uri="mock://inference/mask.tif",
            affected_area=123.4,
            confidence=0.88,
            model_version="1.2.3",
            model_name="fake-ktp-model",
            artifact_uri="mock://models/fake-ktp-model/1.2.3",
            polygons=[],
        )
        return context.inference_result

    def ensure_knowledge(self, context: KtpExecutionContext) -> RagServiceResult:
        context.rag_backend = "fake"
        context.rag_result = RagServiceResult(
            query=context.query,
            summary="fake knowledge summary",
            sources=["fake-source-1"],
            top_k=context.top_k,
            results=[{"chunk_id": "chunk-1", "text": "fake text"}],
        )
        return context.rag_result

    def ensure_report(self, context: KtpExecutionContext) -> ReportServiceResult:
        self.ensure_inference(context)
        if context.extra_params.get("include_knowledge"):
            self.ensure_knowledge(context)
        context.report_backend = "fake"
        context.report_result = ReportServiceResult(
            report_uri="mock://reports/fake-report.html",
            title="fake ktp report",
            sections=["summary", "inference", "confidence"],
            report_id="report-fake-001",
        )
        return context.report_result

    def ensure_confidence(self, context: KtpExecutionContext) -> ConfidenceServiceResult:
        self.ensure_inference(context)
        context.confidence_backend = "fake"
        context.confidence_result = ConfidenceServiceResult(
            image_confidence=0.81,
            text_confidence=0.73,
            workflow_confidence=0.9,
            final_confidence=0.84,
            final_label="high",
            explanation="fake confidence",
        )
        return context.confidence_result

    def ensure_visualization(self, context: KtpExecutionContext) -> VisualizationServiceResult:
        self.ensure_report(context)
        self.ensure_confidence(context)
        context.visualization_backend = "fake"
        context.visualization_result = VisualizationServiceResult(
            visualization_uri="mock://visualizations/fake-dashboard.html",
            title="fake ktp dashboard",
            sections=["overview", "timeline", "artifacts"],
            visualization_id="viz-fake-001",
            artifacts=[],
        )
        return context.visualization_result

    def ensure_training(self, context: KtpExecutionContext) -> TrainingTriggerResult:
        context.training_backend = "fake"
        context.training_result = TrainingTriggerResult(
            training_triggered=True,
            training_job_id="train-fake-001",
            backend="fake",
        )
        return context.training_result


class _FailingKtpServiceBundle(_FakeKtpServiceBundle):
    def ensure_inference(self, context: KtpExecutionContext) -> InferenceServiceResult:
        raise KtpServiceError("forced_real_failure")


def _run_request(
    app,
    method: str,
    path: str,
    payload: dict | None = None,
) -> httpx.Response:
    async def _call() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, json=payload)

    return asyncio.run(_call())


def _build_fake_ktp_app(*, bundle=None, llm_provider=None):
    tool_registry = build_default_tool_registry(
        ktp_knowledge_adapter=KtpKnowledgeAdapter(client=_FakeRagClient()),
        ktp_service_bundle=bundle or _FakeKtpServiceBundle(),
    )
    return create_app(tool_registry_override=tool_registry, llm_provider_override=llm_provider)


def _parse_sse_body(body: str) -> list[dict]:
    events: list[dict] = []
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        for line in block.splitlines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:].strip()))
                break
    return events


def test_v2_health_smoke() -> None:
    app = create_app()
    response = _run_request(app, "GET", "/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_v2_session_and_run_flow() -> None:
    llm_provider = _SequenceStructuredLLMProvider(
        {
            "action": "reply",
            "reasoning": "General greeting should be answered directly.",
            "response_message": "hello from the chat-first agent",
        },
        {
            "action": "reply",
            "reasoning": "General greeting should be answered directly.",
            "response_message": "hello from the chat-first agent",
        }
    )
    app = create_app(llm_provider_override=llm_provider)
    session_response = _run_request(app, "POST", "/v2/sessions", {"title": "Smoke"})
    session_id = session_response.json()["session"]["session_id"]

    run_response = _run_request(
        app,
        "POST",
        f"/v2/sessions/{session_id}/messages",
        {"message": "hello v2"},
    )

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["status"] == "completed"
    assert len(payload["trace"]) >= 2
    assert payload["planner_decision"]["action"] == "reply"
    assert payload["input_context"]["entrypoint"] == "api"
    assert payload["assistant_message"]["parts"][-1]["text"] == "hello from the chat-first agent"

    sessions_response = _run_request(app, "GET", "/v2/sessions")
    assert sessions_response.status_code == 200
    assert any(item["session_id"] == session_id for item in sessions_response.json())

    session_state_response = _run_request(app, "GET", f"/v2/sessions/{session_id}/state")
    assert session_state_response.status_code == 200
    assert session_state_response.json()["latest_run"]["run_id"] == payload["run_id"]

    session_runs_response = _run_request(app, "GET", f"/v2/sessions/{session_id}/runs")
    assert session_runs_response.status_code == 200
    assert len(session_runs_response.json()) == 1

    all_runs_response = _run_request(app, "GET", "/v2/runs")
    assert all_runs_response.status_code == 200
    assert len(all_runs_response.json()) == 1
    assert all_runs_response.json()[0]["run_id"] == payload["run_id"]

    run_trace_response = _run_request(app, "GET", f"/v2/runs/{payload['run_id']}/trace")
    assert run_trace_response.status_code == 200
    assert len(run_trace_response.json()) >= 2

    run_state_response = _run_request(app, "GET", f"/v2/runs/{payload['run_id']}/state")
    assert run_state_response.status_code == 200
    run_state_payload = run_state_response.json()
    assert run_state_payload["run"]["run_id"] == payload["run_id"]
    assert len(run_state_payload["visible_tools"]) >= 1
    assert len(run_state_payload["visible_agents"]) >= 1

    replay_response = _run_request(app, "POST", f"/v2/runs/{payload['run_id']}/replay")
    assert replay_response.status_code == 200
    replay_payload = replay_response.json()
    assert replay_payload["replay_mode"] == "deterministic_dry_replay"
    assert replay_payload["original_state"]["run"]["run_id"] == payload["run_id"]
    assert replay_payload["replayed_state"]["run"]["replay_of_run_id"] == payload["run_id"]
    assert replay_payload["comparison"]["overall_match"] is True
    assert replay_payload["comparison"]["mismatch_fields"] == []


def test_v2_direct_answer_uses_llm_when_configured() -> None:
    app = create_app(
        llm_provider_override=_SequenceStructuredLLMProvider(
            {
                "action": "reply",
                "reasoning": "Identity question should be answered naturally.",
                "response_message": "我是接入共享大模型的通用智能体，也能在需要时切到 KTP 分析工具链。",
            }
        )
    )
    session_response = _run_request(app, "POST", "/v2/sessions", {"title": "LLM Direct Answer"})
    session_id = session_response.json()["session"]["session_id"]

    run_response = _run_request(
        app,
        "POST",
        f"/v2/sessions/{session_id}/messages",
        {"message": "你是？"},
    )

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["status"] == "completed"
    assert payload["planner_decision"]["action"] == "reply"
    assert payload["output_message"] == "我是接入共享大模型的通用智能体，也能在需要时切到 KTP 分析工具链。"
    assert payload["assistant_message"]["parts"][-1]["type"] == "text"


def test_v2_followup_chat_uses_history() -> None:
    llm_provider = _HistoryAwareStructuredLLMProvider(
        {
            "action": "reply",
            "reasoning": "Answer the first question directly.",
            "response_message": "Claude 是 Anthropic 的模型与产品家族。",
        },
        {
            "action": "reply",
            "reasoning": "Use prior context to compare Claude with GPT.",
            "response_message": "Claude 和 GPT 都是大模型产品线，但生态、工具形态和默认交互风格不同。",
        },
    )
    app = create_app(llm_provider_override=llm_provider)
    session_response = _run_request(app, "POST", "/v2/sessions", {"title": "History"})
    session_id = session_response.json()["session"]["session_id"]

    _run_request(
        app,
        "POST",
        f"/v2/sessions/{session_id}/messages",
        {"message": "你知道 Claude 吗？"},
    )
    followup_response = _run_request(
        app,
        "POST",
        f"/v2/sessions/{session_id}/messages",
        {"message": "那和 GPT 有什么差别？"},
    )

    assert followup_response.status_code == 200
    payload = followup_response.json()
    assert payload["status"] == "completed"
    assert "Claude 和 GPT" in payload["output_message"]


def test_v2_planner_trace_marks_schema_alias_application() -> None:
    app = create_app(llm_provider_override=_SchemaAliasStructuredLLMProvider())
    session_response = _run_request(app, "POST", "/v2/sessions", {"title": "Schema Alias"})
    session_id = session_response.json()["session"]["session_id"]

    run_response = _run_request(
        app,
        "POST",
        f"/v2/sessions/{session_id}/messages",
        {"message": "please search workspace for KTP"},
    )

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["status"] == "completed"
    assert any(item["event"] == "llm_schema_alias_applied" for item in payload["trace"])


def test_v2_engine_stream_emits_incremental_events(tmp_path: Path) -> None:
    image_path = tmp_path / "henan_wheat.tif"
    image_path.write_bytes(b"demo")
    app = _build_fake_ktp_app(
        llm_provider=_SequenceStructuredLLMProvider(
            {
                "action": "call_tools",
                "reasoning": "Task request should use the KTP macro tool.",
                "tool_calls": [{"tool_name": "ktp.analysis_pipeline", "tool_input": {}}],
            },
            {
                "action": "reply",
                "reasoning": "Summarize the completed workflow.",
                "response_message": "分析已完成，报告、置信度和可视化产物已经整理好。",
            },
        )
    )
    session = app.state.runtime_store.create_session(
        session_id="stream-session-001",
        title="Stream",
        created_by="test-user",
    )

    events = list(
        app.state.runtime_engine.stream(
            session_id=session.session_id,
            user_message=f"请分析河南小麦长势并生成报告，影像路径是 {image_path}",
            user_id="test-user",
            request_context=None,
        )
    )
    body = "".join(_encode_sse(event) for event in events)
    events = _parse_sse_body(body)

    assert events[0]["event"] == "run.started"
    assert any(item["event"] == "tool.started" for item in events)
    assert any(item["event"] == "tool.completed" for item in events)
    assert any(item["event"] == "artifact.available" for item in events)
    assert any(item["event"] == "assistant.delta" for item in events)
    assert events[-1]["event"] == "run.completed"
    assert events[-1]["run"]["status"] == "completed"


def test_v2_analysis_without_image_path_returns_clarification() -> None:
    app = create_app(
        llm_provider_override=_SequenceStructuredLLMProvider(
            {
                "action": "clarify",
                "reasoning": "Real analysis is missing an image path.",
                "response_message": "要做真实分析，我需要影像路径。请直接发一个本地 .tif 路径。",
            }
        )
    )
    session_response = _run_request(app, "POST", "/v2/sessions", {"title": "Missing Image"})
    session_id = session_response.json()["session"]["session_id"]

    run_response = _run_request(
        app,
        "POST",
        f"/v2/sessions/{session_id}/messages",
        {
            "message": "请分析河南小麦长势并生成报告",
            "context": {"entrypoint": "v2_ui", "extra_params": {}},
        },
    )

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["status"] == "completed"
    assert payload["planner_decision"]["action"] == "clarify"
    assert "影像路径" in payload["output_message"]
    assert payload["tool_invocations"] == []


def test_v2_analysis_with_nonexistent_image_path_returns_clarification() -> None:
    app = create_app(llm_provider_override=_UnexpectedLLMProvider())
    session_response = _run_request(app, "POST", "/v2/sessions", {"title": "Invalid Image"})
    session_id = session_response.json()["session"]["session_id"]

    run_response = _run_request(
        app,
        "POST",
        f"/v2/sessions/{session_id}/messages",
        {
            "message": "请分析河南小麦长势并生成报告，影像路径是 /data/henan_wheat.tif",
            "context": {"entrypoint": "v2_ui", "extra_params": {}},
        },
    )

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["status"] == "completed"
    assert payload["planner_decision"]["action"] == "clarify"
    assert "/data/henan_wheat.tif" in payload["output_message"]
    assert "不存在" in payload["output_message"]
    assert payload["tool_invocations"] == []
    assert payload["observation"]["payload"]["reason"] == "invalid_image_path"
    assert any(item["event"] == "analysis_input_clarification" for item in payload["trace"])


def test_v2_tool_invocation_flow() -> None:
    app = create_app(
        llm_provider_override=_SequenceStructuredLLMProvider(
            {
                "action": "call_tools",
                "reasoning": "Use workspace search for grounded repo lookup.",
                "tool_calls": [{"tool_name": "workspace.search", "tool_input": {"query": "KTP"}}],
            },
            {
                "action": "reply",
                "reasoning": "Summarize the search result.",
                "response_message": "我已经搜索了 workspace，并把命中的文件整理成结果卡片。",
            },
        )
    )
    session_response = _run_request(app, "POST", "/v2/sessions", {"title": "Tool Smoke"})
    session_id = session_response.json()["session"]["session_id"]

    run_response = _run_request(
        app,
        "POST",
        f"/v2/sessions/{session_id}/messages",
        {"message": "please use the demo tool and show an artifact"},
    )

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["status"] == "completed"
    assert payload["planner_decision"]["action"] == "reply"
    assert payload["observation"]["status"] == "success"
    assert payload["tool_invocations"][0]["tool_name"] == "workspace.search"
    assert len(payload["artifacts"]) == 1
    assert payload["assistant_message"]["parts"][0]["type"] == "tool_call"


def test_v2_ktp_knowledge_tool_flow() -> None:
    app = _build_fake_ktp_app(
        llm_provider=_SequenceStructuredLLMProvider(
            {
                "action": "call_tools",
                "reasoning": "The user asked for cited knowledge.",
                "tool_calls": [{"tool_name": "ktp.explain_knowledge", "tool_input": {}}],
            },
            {
                "action": "reply",
                "reasoning": "Return the grounded explanation.",
                "response_message": "NDVI 更强调植被绿度，EVI 对高覆盖度和大气影响更稳健。",
            },
        )
    )
    session_response = _run_request(app, "POST", "/v2/sessions", {"title": "KTP Tool Smoke"})
    session_id = session_response.json()["session"]["session_id"]

    run_response = _run_request(
        app,
        "POST",
        f"/v2/sessions/{session_id}/messages",
        {
            "message": "请用知识资料说明 NDVI 和 EVI 的区别，并给出 source",
            "context": {"entrypoint": "chat", "use_mock": True, "extra_params": {}},
        },
    )

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["status"] == "completed"
    assert payload["agent_steps"][0]["action"] == "call_tools"
    assert payload["observation"]["source"] == "ktp.retrieve_knowledge"
    assert payload["artifacts"][0]["pack_name"] == "ktp"


def test_v2_normalizes_hidden_knowledge_tool_name_to_visible_tool() -> None:
    app = _build_fake_ktp_app(
        llm_provider=_SequenceStructuredLLMProvider(
            {
                "action": "call_tools",
                "reasoning": "The user asked for cited knowledge.",
                "tool_calls": [{"tool_name": "ktp.retrieve_knowledge", "tool_input": {}}],
            },
            {
                "action": "reply",
                "reasoning": "Return the grounded explanation.",
                "response_message": "已经根据知识库整理了 NDVI 和 EVI 的区别。",
            },
        )
    )
    session_response = _run_request(app, "POST", "/v2/sessions", {"title": "KTP Tool Alias"})
    session_id = session_response.json()["session"]["session_id"]

    run_response = _run_request(
        app,
        "POST",
        f"/v2/sessions/{session_id}/messages",
        {
            "message": "请解释 NDVI 和 EVI 的区别，并附上资料来源。",
            "context": {"entrypoint": "chat", "use_mock": True, "extra_params": {}},
        },
    )

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["status"] == "completed"
    assert payload["tool_invocations"][0]["tool_name"] == "ktp.explain_knowledge"


def test_v2_ktp_pack_flow_round_trip(tmp_path: Path) -> None:
    image_path = tmp_path / "henan_wheat_detect.tif"
    image_path.write_bytes(b"demo")
    app = _build_fake_ktp_app(
        llm_provider=_SequenceStructuredLLMProvider(
            {
                "action": "call_tools",
                "reasoning": "Detect entrypoint should execute the macro pipeline.",
                "tool_calls": [{"tool_name": "ktp.analysis_pipeline", "tool_input": {}}],
            },
            {
                "action": "reply",
                "reasoning": "Summarize the finished KTP run.",
                "response_message": "KTP 分析链已经完成，报告、置信度和可视化都已生成。",
            },
        )
    )
    session_response = _run_request(app, "POST", "/v2/sessions", {"title": "KTP Pack Flow"})
    session_id = session_response.json()["session"]["session_id"]

    run_response = _run_request(
        app,
        "POST",
        f"/v2/sessions/{session_id}/messages",
        {
            "message": "Assess wheat health in Henan and build a report.",
            "context": {
                "entrypoint": "detect",
                "region": "henan",
                "crop_type": "wheat",
                "task_type": "crop_health_detection",
                "image_path": str(image_path),
                "use_mock": False,
                "extra_params": {"include_knowledge": True},
            },
        },
    )

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["status"] == "completed"
    assert payload["agent_steps"][0]["action"] == "call_tools"
    assert payload["observation"]["source"] == "ktp.pack_flow"
    assert payload["input_context"]["entrypoint"] == "detect"
    assert payload["input_context"]["conversation_mode"] == "task"
    assert len(payload["tool_invocations"]) == 7
    assert payload["tool_invocations"][0]["tool_name"] == "ktp.analysis_pipeline"
    assert payload["tool_invocations"][1]["tool_name"] == "ktp.lookup_model_registry"
    assert payload["tool_invocations"][-1]["tool_name"] == "ktp.build_visualization"
    assert payload["observation"]["payload"]["knowledge_result"]["summary"] == "fake knowledge summary"
    assert payload["observation"]["payload"]["visualization_result"]["visualization_id"] == "viz-fake-001"


def test_v2_recovers_visible_tool_when_planner_returns_fail_for_analysis_intent() -> None:
    app = _build_fake_ktp_app(
        llm_provider=_SequenceStructuredLLMProvider(
            {
                "action": "fail",
                "reasoning": "The planner could not decide which internal KTP step to use.",
                "response_message": "planner uncertain",
            },
            {
                "action": "reply",
                "reasoning": "Summarize the recovered KTP run.",
                "response_message": "分析已经完成，报告和置信度已生成。",
            },
        )
    )
    session_response = _run_request(app, "POST", "/v2/sessions", {"title": "Recovered Analysis"})
    session_id = session_response.json()["session"]["session_id"]

    run_response = _run_request(
        app,
        "POST",
        f"/v2/sessions/{session_id}/messages",
        {
            "message": "请分析河南小麦长势，并生成报告和置信度说明。",
            "context": {"entrypoint": "chat", "conversation_mode": "chat", "use_mock": True, "extra_params": {}},
        },
    )

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["status"] == "completed"
    assert payload["tool_invocations"][0]["tool_name"] == "ktp.analysis_pipeline"
    assert payload["observation"]["payload"]["report_result"] is not None


def test_v2_tool_catalog_exposes_richer_metadata() -> None:
    app = _build_fake_ktp_app(
        llm_provider=_SequenceStructuredLLMProvider(
            {"action": "reply", "reasoning": "unused", "response_message": "unused"}
        )
    )

    response = _run_request(app, "GET", "/v2/tools")

    assert response.status_code == 200
    payload = response.json()
    analysis_spec = next(item for item in payload if item["name"] == "ktp.analysis_pipeline")
    assert analysis_spec["display_name"] == "KTP analysis pipeline"
    assert analysis_spec["category"] == "analysis"
    assert analysis_spec["is_macro"] is True
    assert analysis_spec["enabled_by_default"] is True
    assert analysis_spec["safety_level"] == "caution"
    workspace_write = next(item for item in payload if item["name"] == "workspace.write")
    assert workspace_write["user_confirmation_required"] is True


def test_v2_pack_flow_extracts_image_path_from_message(tmp_path: Path) -> None:
    image_path = tmp_path / "demo_henan_wheat.tif"
    image_path.write_bytes(b"demo")
    app = _build_fake_ktp_app(
        llm_provider=_SequenceStructuredLLMProvider(
            {
                "action": "call_tools",
                "reasoning": "Use the macro tool and let planner normalize the path.",
                "tool_calls": [{"tool_name": "ktp.analysis_pipeline", "tool_input": {}}],
            },
            {
                "action": "reply",
                "reasoning": "Summarize the finished workflow.",
                "response_message": "分析已经完成。",
            },
        )
    )
    session_response = _run_request(app, "POST", "/v2/sessions", {"title": "KTP Path Parse"})
    session_id = session_response.json()["session"]["session_id"]

    run_response = _run_request(
        app,
        "POST",
        f"/v2/sessions/{session_id}/messages",
        {
            "message": f"请分析河南小麦长势并生成报告，影像路径是 {image_path}",
            "context": {"entrypoint": "v2_ui", "extra_params": {}},
        },
    )

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["status"] == "completed"
    assert payload["agent_steps"][0]["tool_calls"][0]["tool_input"]["image_path"] == str(image_path)
    assert payload["tool_invocations"][1]["tool_input"]["image_path"] == str(image_path)


def test_v2_baldness_request_defaults_scalp_and_hair_context(tmp_path: Path) -> None:
    image_path = tmp_path / "scalp_multispectral.tif"
    image_path.write_bytes(b"demo")
    app = _build_fake_ktp_app(
        llm_provider=_SequenceStructuredLLMProvider(
            {
                "action": "call_tools",
                "reasoning": "Use the analysis pipeline for the baldness task.",
                "tool_calls": [{"tool_name": "ktp.analysis_pipeline", "tool_input": {"crop_type": ""}}],
            },
            {
                "action": "reply",
                "reasoning": "Summarize the finished baldness workflow.",
                "response_message": "斑秃识别流程已经完成。",
            },
        )
    )
    session_response = _run_request(app, "POST", "/v2/sessions", {"title": "Baldness Context"})
    session_id = session_response.json()["session"]["session_id"]

    run_response = _run_request(
        app,
        "POST",
        f"/v2/sessions/{session_id}/messages",
        {
            "message": f"请对这张头皮多光谱影像做真实斑秃识别，并生成分析报告。影像路径是 {image_path}",
            "context": {"entrypoint": "v2_ui", "extra_params": {}},
        },
    )

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["status"] == "completed"
    tool_input = payload["agent_steps"][0]["tool_calls"][0]["tool_input"]
    assert tool_input["region"] == "scalp"
    assert tool_input["crop_type"] == "hair"
    assert tool_input["task_type"] == "baldness_detection"
    assert tool_input["image_path"] == str(image_path)


def test_v2_explicit_training_only_runs_training_tool() -> None:
    app = _build_fake_ktp_app(
        llm_provider=_SequenceStructuredLLMProvider(
            {
                "action": "call_tools",
                "reasoning": "Explicit training intent should only call the training tool.",
                "tool_calls": [{"tool_name": "ktp.trigger_training", "tool_input": {}}],
            },
            {
                "action": "reply",
                "reasoning": "Summarize the training dispatch.",
                "response_message": "训练任务已经显式触发。",
            },
        )
    )
    session_response = _run_request(app, "POST", "/v2/sessions", {"title": "KTP Training"})
    session_id = session_response.json()["session"]["session_id"]

    run_response = _run_request(
        app,
        "POST",
        f"/v2/sessions/{session_id}/messages",
        {
            "message": "please trigger training for rice yield estimation",
            "context": {"entrypoint": "chat", "extra_params": {}, "use_mock": False},
        },
    )

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["tool_invocations"][0]["tool_name"] == "ktp.trigger_training"
    assert payload["observation"]["source"] == "ktp.trigger_training"
    assert payload["observation"]["payload"]["training_result"]["training_job_id"] == "train-fake-001"


def test_v2_real_failure_does_not_fallback_to_mock(tmp_path: Path) -> None:
    image_path = tmp_path / "henan_wheat_failure.tif"
    image_path.write_bytes(b"demo")
    app = _build_fake_ktp_app(
        bundle=_FailingKtpServiceBundle(),
        llm_provider=_SequenceStructuredLLMProvider(
            {
                "action": "call_tools",
                "reasoning": "Run the KTP macro tool for the detect request.",
                "tool_calls": [{"tool_name": "ktp.analysis_pipeline", "tool_input": {}}],
            }
        ),
    )
    session_response = _run_request(app, "POST", "/v2/sessions", {"title": "KTP Failure"})
    session_id = session_response.json()["session"]["session_id"]

    run_response = _run_request(
        app,
        "POST",
        f"/v2/sessions/{session_id}/messages",
        {
            "message": "Assess wheat health in Henan and build a report.",
            "context": {
                "entrypoint": "detect",
                "region": "henan",
                "crop_type": "wheat",
                "task_type": "crop_health_detection",
                "image_path": str(image_path),
                "use_mock": False,
                "extra_params": {},
            },
        },
    )

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["status"] == "failed"
    assert payload["observation"]["status"] == "error"
    assert payload["observation"]["payload"]["failed_step"] == "ktp.run_inference_workflow"
    assert "fallback" not in payload["observation"]["summary"].lower()
    assert payload["tool_invocations"][-1]["status"] == "error"
