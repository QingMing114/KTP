"""Unit tests for unified gateway chat routing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from apps.api_gateway.clients.orchestrator_client import OrchestratorClientError
from apps.api_gateway.schemas.chat import ChatRequest
from apps.api_gateway.services.chat_service import ChatService
from apps.api_gateway.services.chat_runtime_adapter import ChatRuntimeResult
from apps.api_gateway.services.conversation_store import ConversationStore
from services.rag_service.client import RAGServiceClientError
from shared.schemas.orchestrator import WorkflowResponse
from shared.schemas.service_results import RagServiceResult


class _StubRAGClient:
    def __init__(self, result: RagServiceResult | None = None, error: str | None = None) -> None:
        self._result = result
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def run_rag(self, **kwargs: Any) -> RagServiceResult:
        self.calls.append(kwargs)
        if self._error is not None:
            raise RAGServiceClientError(self._error)
        assert self._result is not None
        return self._result


class _DynamicOrchestratorClient:
    def __init__(self, *, error: str | None = None) -> None:
        self._error = error
        self.last_request = None

    def run_workflow(self, request) -> WorkflowResponse:
        self.last_request = request
        if self._error is not None:
            raise OrchestratorClientError(self._error)
        return WorkflowResponse(
            request_id=request.request_id,
            status="completed",
            final_state={
                "task_type": request.task_type or "crop_health_detection",
                "region": request.region,
                "crop_type": request.crop_type,
                "inference_result": {"affected_area": 12.5, "confidence": 0.82},
                "rag_result": {
                    "summary": "Henan wheat health monitoring often considers drought stress.",
                    "sources": ["local://knowledge/henan-wheat"],
                },
                "report_result": {"report_uri": "/tmp/report.html"},
                "confidence_result": {"final_label": "medium", "final_confidence": 0.78},
                "visualization_result": {"visualization_uri": "/tmp/dashboard.html"},
            },
        )


class _StubTextLLMProvider:
    def generate_text(self, *, system_prompt: str, user_prompt: str) -> str:
        assert "遥感知识问答助手" in system_prompt
        assert "检索片段" in user_prompt
        return "这是基于知识库片段整理出的中文回答。"

    def generate_structured(self, *, system_prompt: str, user_prompt: str, response_model):
        raise AssertionError("Structured generation should not be called in chat QA tests.")


class _StubAgentLLMProvider:
    def __init__(
        self,
        *,
        action: str,
        answer: str | None = None,
        reason: str = "llm_dispatch",
        extra_fields: dict[str, Any] | None = None,
    ) -> None:
        self._action = action
        self._answer = answer
        self._reason = reason
        self._extra_fields = extra_fields or {}
        self.structured_calls: list[dict[str, Any]] = []

    def generate_text(self, *, system_prompt: str, user_prompt: str) -> str:
        raise AssertionError("Free-form QA generation should not be called in agent routing tests.")

    def generate_structured(self, *, system_prompt: str, user_prompt: str, response_model):
        self.structured_calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            }
        )
        return response_model.model_validate(
            {
                "action": self._action,
                "reason": self._reason,
                "answer": self._answer,
                **self._extra_fields,
            }
        )


class _StubChatRuntimeAdapter:
    def __init__(self, result: ChatRuntimeResult) -> None:
        self._result = result
        self.calls: list[dict[str, Any]] = []

    def run(self, **kwargs: Any) -> ChatRuntimeResult:
        self.calls.append(kwargs)
        return self._result


class _FailingChatRuntimeAdapter:
    def run(self, **kwargs: Any) -> ChatRuntimeResult:
        raise RuntimeError("runtime exploded")


def _build_service(tmp_path: Path, *, rag_client: _StubRAGClient, orchestrator_client) -> ChatService:
    return ChatService(
        orchestrator_client=orchestrator_client,
        rag_client=rag_client,
        llm_provider=_StubTextLLMProvider(),
        conversation_store=ConversationStore(db_path=str(tmp_path / "chat_test_conversations.sqlite3")),
        history_limit=6,
    )


def test_chat_service_agent_runtime_path_can_be_enabled(tmp_path: Path) -> None:
    rag_client = _StubRAGClient(
        result=RagServiceResult(
            query="unused",
            summary="unused",
            sources=[],
            top_k=0,
            results=[],
        )
    )
    runtime_adapter = _StubChatRuntimeAdapter(
        ChatRuntimeResult(
            success=True,
            response_mode="workflow",
            final_mode="workflow",
            route_reason_suffix="chat_graph:workflow",
            answer="Workflow completed successfully.\n已生成报告结果。",
            workflow_status="completed",
            rag_result=None,
            inference_result={"affected_area": 12.5},
            report_result={"report_uri": "/tmp/report.html"},
            confidence_result={"final_label": "medium"},
            visualization_result=None,
            sources=[],
            context={"chat_runtime_status": "finalized"},
            region="hebei",
            crop_type="wheat",
            task_type="crop_health_detection",
        )
    )
    service = ChatService(
        orchestrator_client=_DynamicOrchestratorClient(),
        rag_client=rag_client,
        llm_provider=None,
        conversation_store=ConversationStore(db_path=str(tmp_path / "chat_runtime_enabled.sqlite3")),
        history_limit=6,
        chat_runtime_adapter=runtime_adapter,
        agent_runtime_enabled=True,
    )

    response = service.handle_chat(
        ChatRequest(
            request_id="req-chat-runtime-enabled-001",
            message="请分析河北省小麦病害情况，并生成报告和置信度说明。",
            mode="agent",
        )
    )

    assert response.success is True
    assert response.mode == "workflow"
    assert "chat_graph:workflow" in response.route_reason
    assert response.workflow_status == "completed"
    assert runtime_adapter.calls


def test_chat_service_runtime_failure_falls_back_to_legacy_agent(tmp_path: Path) -> None:
    rag_client = _StubRAGClient(
        result=RagServiceResult(
            query="unused",
            summary="unused",
            sources=[],
            top_k=0,
            results=[],
        )
    )
    service = ChatService(
        orchestrator_client=_DynamicOrchestratorClient(),
        rag_client=rag_client,
        llm_provider=_StubAgentLLMProvider(
            action="direct_answer",
            answer="这是 legacy fallback 的直接回答。",
            reason="llm_dispatch",
        ),
        conversation_store=ConversationStore(db_path=str(tmp_path / "chat_runtime_fallback.sqlite3")),
        history_limit=6,
        chat_runtime_adapter=_FailingChatRuntimeAdapter(),
        agent_runtime_enabled=True,
    )

    response = service.handle_chat(
        ChatRequest(
            request_id="req-chat-runtime-fallback-001",
            message="NDVI 和 EVI 有什么区别？",
            mode="agent",
        )
    )

    assert response.success is True
    assert response.mode == "agent"
    assert "runtime_fallback" in response.route_reason
    assert response.answer == "这是 legacy fallback 的直接回答。"
    turns = service._conversation_store.get_recent_turns(  # type: ignore[attr-defined]
        user_id="anonymous",
        conversation_id=response.conversation_id,
        limit=1,
    )
    assert turns[0].context["agent_audit"]["path"] == "legacy_fallback"
    assert turns[0].context["agent_audit"]["legacy_fallback_used"] is True


def test_chat_service_runtime_failure_respects_disabled_legacy_fallback(tmp_path: Path) -> None:
    rag_client = _StubRAGClient(
        result=RagServiceResult(
            query="unused",
            summary="unused",
            sources=[],
            top_k=0,
            results=[],
        )
    )
    service = ChatService(
        orchestrator_client=_DynamicOrchestratorClient(),
        rag_client=rag_client,
        llm_provider=_StubAgentLLMProvider(
            action="direct_answer",
            answer="不应被使用。",
            reason="llm_dispatch",
        ),
        conversation_store=ConversationStore(db_path=str(tmp_path / "chat_runtime_no_legacy.sqlite3")),
        history_limit=6,
        chat_runtime_adapter=_FailingChatRuntimeAdapter(),
        agent_runtime_enabled=True,
        agent_legacy_fallback_enabled=False,
    )

    response = service.handle_chat(
        ChatRequest(
            request_id="req-chat-runtime-no-legacy-001",
            message="NDVI 和 EVI 有什么区别？",
            mode="agent",
        )
    )

    assert response.success is False
    assert "legacy_disabled" in response.route_reason
    turns = service._conversation_store.get_recent_turns(  # type: ignore[attr-defined]
        user_id="anonymous",
        conversation_id=response.conversation_id,
        limit=1,
    )
    assert turns[0].context["agent_audit"]["legacy_fallback_enabled"] is False


def test_chat_service_shadow_compare_records_legacy_result(tmp_path: Path) -> None:
    rag_client = _StubRAGClient(
        result=RagServiceResult(query="unused", summary="", sources=[], top_k=0, results=[])
    )
    conversation_store = ConversationStore(db_path=str(tmp_path / "chat_shadow_compare.sqlite3"))
    runtime_adapter = _StubChatRuntimeAdapter(
        ChatRuntimeResult(
            success=True,
            response_mode="agent",
            final_mode="direct_answer",
            route_reason_suffix="chat_graph:direct_answer",
            answer="这是 runtime 的直接回答。",
            workflow_status=None,
            rag_result=None,
            inference_result=None,
            report_result=None,
            confidence_result=None,
            visualization_result=None,
            sources=[],
            context={"chat_runtime_status": "finalized"},
            region=None,
            crop_type=None,
            task_type="crop_health_detection",
        )
    )
    service = ChatService(
        orchestrator_client=_DynamicOrchestratorClient(),
        rag_client=rag_client,
        llm_provider=_StubAgentLLMProvider(
            action="direct_answer",
            answer="这是 legacy shadow 的直接回答。",
            reason="llm_dispatch",
        ),
        conversation_store=conversation_store,
        history_limit=6,
        chat_runtime_adapter=runtime_adapter,
        agent_runtime_enabled=True,
        agent_shadow_compare_enabled=True,
    )

    response = service.handle_chat(
        ChatRequest(
            request_id="req-chat-shadow-001",
            message="NDVI 和 EVI 有什么区别？",
            mode="agent",
        )
    )

    assert response.success is True
    turns = conversation_store.get_recent_turns(
        user_id="anonymous",
        conversation_id=response.conversation_id,
        limit=1,
    )
    assert turns
    shadow_compare = turns[0].context["shadow_compare"]
    agent_audit = turns[0].context["agent_audit"]
    assert shadow_compare["enabled"] is True
    assert shadow_compare["status"] == "completed"
    assert shadow_compare["mode"] == "agent"
    assert shadow_compare["primary_mode"] == "agent"
    assert shadow_compare["primary_success"] is True
    assert shadow_compare["comparison"]["mode_match"] is True
    assert shadow_compare["comparison"]["success_match"] is True
    assert agent_audit["path"] == "runtime_first"
    assert agent_audit["shadow_compare_enabled"] is True
    assert agent_audit["shadow_compare_status"] == "completed"
    assert agent_audit["shadow_compare_mode_match"] is True


def test_chat_service_routes_plain_question_to_qa(tmp_path: Path) -> None:
    rag_client = _StubRAGClient(
        result=RagServiceResult(
            query="河南小麦监测常见影响因素有哪些？",
            summary="Henan wheat monitoring often considers drought stress.",
            sources=["local://knowledge/henan-wheat"],
            top_k=1,
            results=[
                {
                    "chunk_id": "chunk-1",
                    "document_id": "doc-1",
                    "text": "Henan wheat monitoring often considers drought stress, disease pressure, and agronomic response plans.",
                    "source": "local://knowledge/henan-wheat",
                    "score": 0.91,
                    "metadata": {"region": "henan", "crop_type": "wheat"},
                }
            ],
        )
    )
    service = _build_service(
        tmp_path,
        rag_client=rag_client,
        orchestrator_client=_DynamicOrchestratorClient(),
    )

    response = service.handle_chat(
        ChatRequest(
            request_id="req-chat-service-qa-001",
            message="河南小麦监测常见影响因素有哪些？",
            mode="qa",
        )
    )

    assert response.success is True
    assert response.mode == "qa"
    assert response.route_reason == "explicit:qa"
    assert response.answer == "这是基于知识库片段整理出的中文回答。"
    assert response.rag_result is not None
    assert response.sources == ["local://knowledge/henan-wheat"]
    assert response.conversation_id
    assert response.history_turn_count == 0
    assert rag_client.calls[0]["user_query"] == "河南小麦监测常见影响因素有哪些？"


def test_chat_service_inherits_qa_context_for_follow_up_question(tmp_path: Path) -> None:
    rag_client = _StubRAGClient(
        result=RagServiceResult(
            query="NDVI 和 EVI 的差异",
            summary="EVI is often more stable in high biomass regions.",
            sources=["local://knowledge/vegetation-index"],
            top_k=1,
            results=[
                {
                    "chunk_id": "chunk-qa-1",
                    "document_id": "doc-qa-1",
                    "text": "EVI is often more stable than NDVI in high biomass regions.",
                    "source": "local://knowledge/vegetation-index",
                    "score": 0.88,
                    "metadata": {"topic": "vegetation-index"},
                }
            ],
        )
    )
    service = _build_service(
        tmp_path,
        rag_client=rag_client,
        orchestrator_client=_DynamicOrchestratorClient(),
    )

    first = service.handle_chat(
        ChatRequest(
            request_id="req-chat-service-qa-followup-001",
            message="NDVI 和 EVI 有什么区别？",
            mode="qa",
        )
    )
    second = service.handle_chat(
        ChatRequest(
            request_id="req-chat-service-qa-followup-002",
            conversation_id=first.conversation_id,
            message="那它更适合高植被覆盖区吗？",
            mode="qa",
        )
    )

    assert second.success is True
    assert second.mode == "qa"
    assert second.route_reason == "explicit:qa"
    assert second.history_turn_count == 1
    assert len(rag_client.calls) == 2
    assert "上一轮用户消息：NDVI 和 EVI 有什么区别？" in rag_client.calls[1]["user_query"]
    assert "当前追问：那它更适合高植被覆盖区吗？" in rag_client.calls[1]["user_query"]
    assert "conversation_history" in rag_client.calls[1]["context"]


def test_chat_service_routes_task_request_to_workflow(tmp_path: Path) -> None:
    rag_client = _StubRAGClient(
        result=RagServiceResult(query="unused", summary="", sources=[], top_k=0, results=[])
    )
    orchestrator_client = _DynamicOrchestratorClient()
    service = _build_service(
        tmp_path,
        rag_client=rag_client,
        orchestrator_client=orchestrator_client,
    )

    response = service.handle_chat(
        ChatRequest(
            request_id="req-chat-service-wf-001",
            message="请分析河南小麦长势，并生成报告和置信度说明。",
            mode="workflow",
            region="henan",
            crop_type="wheat",
            use_mock=True,
        )
    )

    assert response.success is True
    assert response.mode == "workflow"
    assert response.route_reason == "explicit:workflow"
    assert response.workflow_status == "completed"
    assert response.report_result == {"report_uri": "/tmp/report.html"}
    assert response.visualization_result == {"visualization_uri": "/tmp/dashboard.html"}
    assert "工作流完成处理" in response.answer
    assert response.sources == ["local://knowledge/henan-wheat"]
    assert response.conversation_id
    assert response.history_turn_count == 0
    assert orchestrator_client.last_request.region == "henan"


def test_chat_service_inherits_workflow_fields_for_follow_up(tmp_path: Path) -> None:
    rag_client = _StubRAGClient(
        result=RagServiceResult(query="unused", summary="", sources=[], top_k=0, results=[])
    )
    orchestrator_client = _DynamicOrchestratorClient()
    service = _build_service(
        tmp_path,
        rag_client=rag_client,
        orchestrator_client=orchestrator_client,
    )

    first = service.handle_chat(
        ChatRequest(
            request_id="req-chat-service-wf-followup-001",
            message="请分析河南小麦长势，并生成报告和置信度说明。",
            mode="workflow",
            region="henan",
            crop_type="wheat",
            task_type="crop_health_detection",
            use_mock=True,
        )
    )
    second = service.handle_chat(
        ChatRequest(
            request_id="req-chat-service-wf-followup-002",
            conversation_id=first.conversation_id,
            message="那再来一次",
            mode="workflow",
        )
    )

    assert second.success is True
    assert second.mode == "workflow"
    assert second.route_reason == "explicit:workflow"
    assert second.history_turn_count == 1
    assert orchestrator_client.last_request.region == "henan"
    assert orchestrator_client.last_request.crop_type == "wheat"
    assert orchestrator_client.last_request.task_type == "crop_health_detection"
    assert orchestrator_client.last_request.use_mock is True
    assert orchestrator_client.last_request.extra_params["inherited_fields"] == [
        "region",
        "crop_type",
        "task_type",
        "use_mock",
    ]


def test_chat_service_returns_structured_failure_when_rag_errors(tmp_path: Path) -> None:
    service = _build_service(
        tmp_path,
        rag_client=_StubRAGClient(error="vector store unavailable"),
        orchestrator_client=_DynamicOrchestratorClient(),
    )

    response = service.handle_chat(
        ChatRequest(
            request_id="req-chat-service-fail-001",
            message="NDVI 和 EVI 有什么区别？",
            mode="qa",
        )
    )

    assert response.success is False
    assert response.mode == "qa"
    assert response.route_reason == "explicit:qa"
    assert response.message == "vector store unavailable"
    assert "知识问答检索失败" in response.answer
    assert response.conversation_id
    assert response.history_turn_count == 0


def test_chat_service_auto_prefers_agent_direct_answer_when_llm_available(tmp_path: Path) -> None:
    rag_client = _StubRAGClient(
        result=RagServiceResult(query="unused", summary="", sources=[], top_k=0, results=[])
    )
    orchestrator_client = _DynamicOrchestratorClient()
    llm_provider = _StubAgentLLMProvider(
        action="direct_answer",
        answer="NDVI 主要使用红光与近红外，EVI 在高植被覆盖区通常更稳健，并增加了蓝光校正。",
        reason="general_remote_sensing_knowledge",
    )
    service = ChatService(
        orchestrator_client=orchestrator_client,
        rag_client=rag_client,
        llm_provider=llm_provider,
        conversation_store=ConversationStore(db_path=str(tmp_path / "chat_agent_conversations.sqlite3")),
        history_limit=6,
    )

    response = service.handle_chat(
        ChatRequest(
            request_id="req-chat-service-agent-001",
            message="NDVI 和 EVI 有什么区别？",
        )
    )

    assert response.success is True
    assert response.mode == "agent"
    assert response.route_reason == "auto:agent_llm:direct_answer"
    assert "高植被覆盖区" in response.answer
    assert response.rag_result is None
    assert response.workflow_status is None
    assert len(llm_provider.structured_calls) == 1
    assert not rag_client.calls
    assert orchestrator_client.last_request is None


def test_chat_service_auto_prefers_runtime_when_enabled_without_llm(tmp_path: Path) -> None:
    rag_client = _StubRAGClient(
        result=RagServiceResult(query="unused", summary="", sources=[], top_k=0, results=[])
    )
    runtime_adapter = _StubChatRuntimeAdapter(
        ChatRuntimeResult(
            success=True,
            response_mode="agent",
            final_mode="direct_answer",
            route_reason_suffix="chat_graph:direct_answer",
            answer="这是 runtime 启发式直接回答。",
            workflow_status=None,
            rag_result=None,
            inference_result=None,
            report_result=None,
            confidence_result=None,
            visualization_result=None,
            sources=[],
            context={"chat_runtime_status": "finalized"},
            region=None,
            crop_type=None,
            task_type="crop_health_detection",
        )
    )
    service = ChatService(
        orchestrator_client=_DynamicOrchestratorClient(),
        rag_client=rag_client,
        llm_provider=None,
        conversation_store=ConversationStore(db_path=str(tmp_path / "chat_auto_runtime.sqlite3")),
        history_limit=6,
        chat_runtime_adapter=runtime_adapter,
        agent_runtime_enabled=True,
    )

    response = service.handle_chat(
        ChatRequest(
            request_id="req-chat-service-agent-001b",
            message="NDVI 和 EVI 有什么区别？",
            mode="auto",
        )
    )

    assert response.success is True
    assert response.mode == "agent"
    assert response.route_reason == "auto:agent_runtime:chat_graph:direct_answer"
    assert response.answer == "这是 runtime 启发式直接回答。"
    assert runtime_adapter.calls


def test_chat_service_agent_routes_to_workflow_when_llm_requests_it(tmp_path: Path) -> None:
    rag_client = _StubRAGClient(
        result=RagServiceResult(query="unused", summary="", sources=[], top_k=0, results=[])
    )
    orchestrator_client = _DynamicOrchestratorClient()

    class _WorkflowAgentLLMProvider(_StubAgentLLMProvider):
        def generate_structured(self, *, system_prompt: str, user_prompt: str, response_model):
            self.structured_calls.append(
                {
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                }
            )
            return response_model.model_validate(
                {
                    "action": "workflow",
                    "reason": "requires_image_analysis_outputs",
                    "workflow_message": "请分析河南小麦长势，并生成报告和置信度说明。",
                    "region": "henan",
                    "crop_type": "wheat",
                    "task_type": "crop_health_detection",
                }
            )

    llm_provider = _WorkflowAgentLLMProvider(action="workflow")
    service = ChatService(
        orchestrator_client=orchestrator_client,
        rag_client=rag_client,
        llm_provider=llm_provider,
        conversation_store=ConversationStore(db_path=str(tmp_path / "chat_agent_workflow.sqlite3")),
        history_limit=6,
    )

    response = service.handle_chat(
        ChatRequest(
            request_id="req-chat-service-agent-002",
            message="帮我看看这块河南小麦，并给报告。",
        )
    )

    assert response.success is True
    assert response.mode == "workflow"
    assert response.route_reason == "auto:agent_llm:workflow:requires_image_analysis_outputs"
    assert response.workflow_status == "completed"
    assert orchestrator_client.last_request is not None
    assert orchestrator_client.last_request.region == "henan"
    assert orchestrator_client.last_request.crop_type == "wheat"
    assert orchestrator_client.last_request.task_type == "crop_health_detection"


def test_chat_service_agent_normalizes_region_crop_and_task_before_workflow(tmp_path: Path) -> None:
    rag_client = _StubRAGClient(
        result=RagServiceResult(query="unused", summary="", sources=[], top_k=0, results=[])
    )
    orchestrator_client = _DynamicOrchestratorClient()
    llm_provider = _StubAgentLLMProvider(
        action="workflow",
        reason="requires_workflow_execution",
        extra_fields={
            "workflow_message": "请分析河北省小麦病害情况，并生成报告。",
            "region": "河北省",
            "crop_type": "小麦",
            "task_type": "disease_detection",
        },
    )
    service = ChatService(
        orchestrator_client=orchestrator_client,
        rag_client=rag_client,
        llm_provider=llm_provider,
        conversation_store=ConversationStore(db_path=str(tmp_path / "chat_agent_normalize.sqlite3")),
        history_limit=6,
    )

    response = service.handle_chat(
        ChatRequest(
            request_id="req-chat-service-agent-003",
            message="帮我看看河北省小麦病害情况，并给报告。",
            mode="agent",
        )
    )

    assert response.success is True
    assert response.mode == "workflow"
    assert response.route_reason == "explicit:agent:workflow:requires_workflow_execution"
    assert orchestrator_client.last_request is not None
    assert orchestrator_client.last_request.region == "hebei"
    assert orchestrator_client.last_request.crop_type == "wheat"
    assert orchestrator_client.last_request.task_type == "crop_health_detection"


def test_chat_service_isolates_history_by_user_id(tmp_path: Path) -> None:
    rag_client = _StubRAGClient(
        result=RagServiceResult(
            query="NDVI 和 EVI 的差异",
            summary="EVI is often more stable in high biomass regions.",
            sources=["local://knowledge/vegetation-index"],
            top_k=1,
            results=[
                {
                    "chunk_id": "chunk-qa-1",
                    "document_id": "doc-qa-1",
                    "text": "EVI is often more stable than NDVI in high biomass regions.",
                    "source": "local://knowledge/vegetation-index",
                    "score": 0.88,
                    "metadata": {"topic": "vegetation-index"},
                }
            ],
        )
    )
    service = _build_service(
        tmp_path,
        rag_client=rag_client,
        orchestrator_client=_DynamicOrchestratorClient(),
    )

    first = service.handle_chat(
        ChatRequest(
            request_id="req-chat-service-user-001",
            user_id="user-a",
            message="NDVI 和 EVI 有什么区别？",
            mode="qa",
        )
    )
    second = service.handle_chat(
        ChatRequest(
            request_id="req-chat-service-user-002",
            user_id="user-b",
            conversation_id=first.conversation_id,
            message="那它更适合高植被覆盖区吗？",
            mode="qa",
        )
    )

    assert first.user_id == "user-a"
    assert second.user_id == "user-b"
    assert second.history_turn_count == 0
    assert second.route_reason == "explicit:qa"
    assert "上一轮用户消息" not in rag_client.calls[1]["user_query"]
