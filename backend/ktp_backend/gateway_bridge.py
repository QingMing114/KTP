"""Gateway compatibility bridge for the standalone KTP backend."""

from __future__ import annotations

import os
from uuid import uuid4

from apps.api_gateway.schemas.agent import GatewayAgentResponse, GatewayDebugView, GatewayWorkflowView
from apps.api_gateway.schemas.chat import ChatRequest
from apps.api_gateway.schemas.detect import DetectRequest
from v2.runtime.engine import BoundedRuntimeEngine
from v2.runtime.store import RuntimeStore
from v2.shared.schemas import AttachmentV2, RequestContextV2, RunDetail, SessionMessage


class GatewayRuntimeBridge:
    """Thin bridge between public gateway routes and the standalone backend runtime."""

    def __init__(
        self,
        *,
        runtime_store: RuntimeStore,
        runtime_engine: BoundedRuntimeEngine,
    ) -> None:
        self._runtime_store = runtime_store
        self._runtime_engine = runtime_engine

    def handle_chat(self, request: ChatRequest, *, public_base_url: str) -> GatewayAgentResponse:
        request_id = request.request_id or str(uuid4())
        conversation_id = request.conversation_id or str(uuid4())
        user_id = (request.user_id or "anonymous").strip() or "anonymous"
        extra_params = dict(request.extra_params)
        if request.top_k is not None:
            extra_params["top_k"] = request.top_k
        extra_params.setdefault("client_request_id", request_id)
        session = self._ensure_session(
            session_id=conversation_id,
            title=self._build_session_title(request.message),
            created_by=user_id,
        )
        request_context = self._merge_chat_context(
            session_id=session.session_id,
            request_context=RequestContextV2(
                entrypoint="chat",
                conversation_mode="chat",
                region=request.region,
                crop_type=request.crop_type,
                task_type=request.task_type,
                image_path=request.image_path,
                use_mock=request.use_mock,
                attachments=(
                    [AttachmentV2(path=request.image_path, name=os.path.basename(request.image_path))]
                    if request.image_path
                    else []
                ),
                extra_params=extra_params,
            ),
        )
        run = self._runtime_engine.run(
            session_id=session.session_id,
            user_message=request.message,
            user_id=user_id,
            request_context=request_context,
        )
        return self._build_gateway_response(
            request_id=request_id,
            conversation_id=conversation_id,
            run=run,
            public_base_url=public_base_url,
        )

    def handle_detect(self, request: DetectRequest, *, public_base_url: str) -> GatewayAgentResponse:
        session_id = str(uuid4())
        extra_params = dict(request.extra_params)
        extra_params.setdefault("client_request_id", request.request_id)
        session = self._ensure_session(
            session_id=session_id,
            title=self._build_session_title(request.user_query, prefix="Detect"),
            created_by="detect-api",
        )
        run = self._runtime_engine.run(
            session_id=session.session_id,
            user_message=request.user_query,
            user_id="detect-api",
            request_context=RequestContextV2(
                entrypoint="detect",
                conversation_mode="task",
                region=request.region,
                crop_type=request.crop_type,
                task_type=request.task_type,
                image_path=request.image_path,
                use_mock=request.use_mock,
                attachments=(
                    [AttachmentV2(path=request.image_path, name=os.path.basename(request.image_path))]
                    if request.image_path
                    else []
                ),
                extra_params=extra_params,
            ),
        )
        return self._build_gateway_response(
            request_id=request.request_id,
            conversation_id=session_id,
            run=run,
            public_base_url=public_base_url,
        )

    def handle_openai_chat(
        self,
        *,
        model: str,
        messages: list[SessionMessage],
        user_id: str | None,
        conversation_id: str | None,
        public_base_url: str,
    ) -> GatewayAgentResponse:
        user_message_index = self._find_last_user_message_index(messages)
        if user_message_index is None:
            raise ValueError("openai_request_requires_user_message")
        current_message = messages[user_message_index]
        history = messages[:user_message_index]
        session_id = conversation_id or str(uuid4())
        existing_session = self._runtime_store.get_session(session_id)
        if existing_session is None:
            session = self._runtime_store.create_session(
                session_id=session_id,
                title=self._build_session_title(current_message.content, prefix="OpenAI"),
                created_by=user_id or "openai-client",
            )
            for item in history:
                self._runtime_store.append_message(session.session_id, item)
        return self.handle_chat(
            ChatRequest(
                conversation_id=session_id,
                user_id=user_id or "openai-client",
                message=current_message.content,
                extra_params={
                    "source": "openai_compatible",
                    "openai_model": model,
                },
            ),
            public_base_url=public_base_url,
        )

    def _ensure_session(self, *, session_id: str, title: str, created_by: str | None):
        session = self._runtime_store.get_session(session_id)
        if session is not None:
            return session
        return self._runtime_store.create_session(
            session_id=session_id,
            title=title,
            created_by=created_by,
        )

    def _merge_chat_context(
        self,
        *,
        session_id: str,
        request_context: RequestContextV2,
    ) -> RequestContextV2:
        session = self._runtime_store.get_session(session_id)
        if session is None or session.latest_run_id is None:
            return request_context
        latest_run = self._runtime_store.get_run(session.latest_run_id)
        previous_context = latest_run.input_context if latest_run is not None else None
        if previous_context is None:
            return request_context
        merged_extra_params = dict(previous_context.extra_params)
        merged_extra_params.update(request_context.extra_params)
        return RequestContextV2(
            entrypoint=request_context.entrypoint,
            conversation_mode=request_context.conversation_mode,
            region=request_context.region or previous_context.region,
            crop_type=request_context.crop_type or previous_context.crop_type,
            task_type=request_context.task_type or previous_context.task_type,
            image_path=request_context.image_path or previous_context.image_path,
            use_mock=request_context.use_mock
            if request_context.use_mock is not None
            else previous_context.use_mock,
            attachments=request_context.attachments or previous_context.attachments,
            client_capabilities={
                **previous_context.client_capabilities,
                **request_context.client_capabilities,
            },
            extra_params=merged_extra_params,
        )

    @staticmethod
    def _find_last_user_message_index(messages: list[SessionMessage]) -> int | None:
        for index in range(len(messages) - 1, -1, -1):
            item = messages[index]
            if item.role == "user" and item.content.strip():
                return index
        return None

    @staticmethod
    def _build_workflow(run: RunDetail) -> GatewayWorkflowView:
        payload = run.observation.payload if run.observation is not None else {}
        knowledge_result = payload.get("knowledge_result")
        if knowledge_result is None and run.observation is not None and run.observation.source == "ktp.retrieve_knowledge":
            knowledge_result = {
                "query": payload.get("query"),
                "summary": payload.get("summary"),
                "sources": payload.get("sources", []),
                "top_k": payload.get("top_k"),
                "result_count": payload.get("result_count"),
            }
        return GatewayWorkflowView(
            model_registry_result=payload.get("model_registry_result"),
            inference_result=payload.get("inference_result"),
            knowledge_result=knowledge_result,
            report_result=payload.get("report_result"),
            confidence_result=payload.get("confidence_result"),
            visualization_result=payload.get("visualization_result"),
            training_result=payload.get("training_result"),
        )

    @staticmethod
    def _extract_sources(run: RunDetail) -> list[str]:
        if run.observation is None:
            return []
        payload = run.observation.payload
        knowledge_result = payload.get("knowledge_result") or payload.get("rag_result")
        if isinstance(knowledge_result, dict):
            raw_sources = knowledge_result.get("sources", [])
            if isinstance(raw_sources, list):
                return [str(item) for item in raw_sources]
        raw_sources = payload.get("sources", [])
        if isinstance(raw_sources, list):
            return [str(item) for item in raw_sources]
        return []

    @staticmethod
    def _flatten_answer(run: RunDetail) -> str:
        if run.assistant_message is None:
            return run.output_message
        text_parts = [
            (part.text or "").strip()
            for part in run.assistant_message.parts
            if part.type in {"text", "status", "error"} and (part.text or "").strip()
        ]
        if text_parts:
            return "\n".join(text_parts)
        return run.output_message

    def _build_gateway_response(
        self,
        *,
        request_id: str,
        conversation_id: str,
        run: RunDetail,
        public_base_url: str,
    ) -> GatewayAgentResponse:
        workflow = self._build_workflow(run)
        return GatewayAgentResponse(
            request_id=request_id,
            conversation_id=conversation_id,
            session_id=run.session_id,
            run_id=run.run_id,
            status=run.status,
            answer=self._flatten_answer(run),
            assistant_message=run.assistant_message,
            artifacts=run.artifacts,
            sources=self._extract_sources(run),
            tool_invocations=run.tool_invocations,
            workflow=workflow,
            debug=GatewayDebugView(
                session_url=f"{public_base_url}/v2/sessions/{run.session_id}",
                run_url=f"{public_base_url}/v2/runs/{run.run_id}",
                trace_url=f"{public_base_url}/v2/runs/{run.run_id}/trace",
                replay_url=f"{public_base_url}/v2/runs/{run.run_id}/replay",
                ui_url=f"{public_base_url}/v2/ui?session_id={run.session_id}&run_id={run.run_id}",
            ),
        )

    @staticmethod
    def _build_session_title(message: str, *, prefix: str = "KTP") -> str:
        trimmed = " ".join(message.strip().split())
        if not trimmed:
            return f"{prefix} Session"
        return f"{prefix} {trimmed[:48]}"

