from __future__ import annotations

from apps.api_gateway.schemas.chat import ChatRequest
from apps.api_gateway.services.gateway_agent_service import GatewayAgentService
from v2.runtime.store import InMemoryRuntimeStore
from v2.shared.schemas import RunDetail


class _CapturingRuntimeEngine:
    def __init__(self, store: InMemoryRuntimeStore) -> None:
        self._store = store
        self.calls: list[dict[str, object]] = []
        self._run_counter = 0

    def run(self, *, session_id: str, user_message: str, user_id: str | None, request_context):
        self._run_counter += 1
        run = RunDetail(
            run_id=f"run-{self._run_counter:03d}",
            session_id=session_id,
            status="completed",
            input_message=user_message,
            input_context=request_context,
            output_message="ok",
            tool_invocations=[],
            artifacts=[],
            trace=[],
        )
        self.calls.append(
            {
                "session_id": session_id,
                "user_message": user_message,
                "user_id": user_id,
                "request_context": request_context,
            }
        )
        self._store.save_run(run)
        session = self._store.get_session(session_id)
        assert session is not None
        session.latest_run_id = run.run_id
        self._store.save_session(session)
        return run


def test_gateway_agent_service_forwards_top_k_and_client_request_id() -> None:
    store = InMemoryRuntimeStore()
    engine = _CapturingRuntimeEngine(store)
    service = GatewayAgentService(runtime_store=store, runtime_engine=engine)

    response = service.handle_chat(
        ChatRequest(
            request_id="req-chat-top-k-001",
            message="请解释 NDVI 和 EVI 的区别",
            top_k=5,
            extra_params={"include_knowledge": True},
        ),
        public_base_url="http://testserver",
    )

    assert response.request_id == "req-chat-top-k-001"
    assert len(engine.calls) == 1
    request_context = engine.calls[0]["request_context"]
    assert request_context.extra_params["top_k"] == 5
    assert request_context.extra_params["client_request_id"] == "req-chat-top-k-001"
    assert request_context.extra_params["include_knowledge"] is True


def test_gateway_agent_service_reuses_previous_extra_params_for_followup_chat() -> None:
    store = InMemoryRuntimeStore()
    engine = _CapturingRuntimeEngine(store)
    service = GatewayAgentService(runtime_store=store, runtime_engine=engine)

    service.handle_chat(
        ChatRequest(
            request_id="req-chat-followup-001",
            conversation_id="conv-followup-001",
            message="请分析河南小麦长势",
            region="henan",
            top_k=7,
            extra_params={"include_visualization": True},
        ),
        public_base_url="http://testserver",
    )

    service.handle_chat(
        ChatRequest(
            request_id="req-chat-followup-002",
            conversation_id="conv-followup-001",
            message="再来一次，保留之前的参数",
            extra_params={},
        ),
        public_base_url="http://testserver",
    )

    assert len(engine.calls) == 2
    request_context = engine.calls[1]["request_context"]
    assert request_context.region == "henan"
    assert request_context.extra_params["top_k"] == 7
    assert request_context.extra_params["include_visualization"] is True
    assert request_context.extra_params["client_request_id"] == "req-chat-followup-002"
