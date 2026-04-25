"""Unified chat service that auto-routes QA and workflow requests."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from apps.api_gateway.clients.orchestrator_client import (
    LocalOrchestratorClient,
    OrchestratorClientError,
)
from apps.api_gateway.schemas.chat import ChatRequest, ChatResponse
from apps.api_gateway.services.conversation_store import (
    ConversationStore,
    ConversationStoreError,
    ConversationTurn,
)
from apps.api_gateway.services.chat_runtime_adapter import ChatRuntimeAdapter
from infra.llm.provider import AgentLLMError, AgentLLMProvider
from services.rag_service.client import LocalRAGServiceClient, RAGServiceClientError
from shared.request_normalization import (
    detect_crop_type_from_text,
    detect_region_from_text,
    detect_task_type_from_text,
    normalize_crop_type,
    normalize_region,
    normalize_task_type,
)
from shared.schemas.orchestrator import WorkflowRequest
from shared.schemas.service_results import RagServiceResult

logger = logging.getLogger(__name__)

ResolvedMode = Literal["agent", "qa", "workflow"]

_AUTO_WORKFLOW_IMAGE_KEYWORDS = (
    "这张图",
    "这张影像",
    "这幅图",
    "这景影像",
    "这张遥感图",
    "this image",
    "this raster",
    "this scene",
)
_AUTO_WORKFLOW_IMPERATIVE_KEYWORDS = (
    "请分析",
    "请检测",
    "请识别",
    "请分割",
    "请估算",
    "请反演",
    "再分析",
    "再做一次",
    "再跑一次",
    "analyze ",
    "assess ",
    "detect ",
    "segment ",
    "estimate ",
    "invert ",
)
_AUTO_WORKFLOW_OUTPUT_KEYWORDS = (
    "生成报告",
    "输出报告",
    "给出报告",
    "置信度说明",
    "置信度",
    "可视化",
    "workflow",
    "generate report",
    "provide a report",
    "with confidence",
    "visualization",
)
_AUTO_WORKFLOW_TASK_KEYWORDS = (
    "检测",
    "识别",
    "分割",
    "估产",
    "反演",
    "地物分类",
    "land cover analysis",
    "yield estimation",
    "lai inversion",
)
_AUTO_QA_KNOWLEDGE_KEYWORDS = (
    "什么是",
    "有什么区别",
    "区别",
    "原理",
    "为什么",
    "为何",
    "如何",
    "怎么",
    "哪些",
    "介绍一下",
    "explain",
    "what is",
    "difference",
    "why",
    "how",
)
_FOLLOW_UP_KEYWORDS = (
    "那",
    "那么",
    "这个",
    "这个结果",
    "它",
    "继续",
    "继续说",
    "然后",
    "再来一次",
    "再做一次",
    "再跑一次",
    "换成",
    "同一张",
    "同一区域",
    "同一块地",
    "上一轮",
    "上一次",
    "what about",
    "then",
    "continue",
    "same image",
    "same region",
)
_NO_RAG_RESULT_SUMMARY = "No relevant knowledge snippets were retrieved."


class _AgentRouteDecision(BaseModel):
    """Structured LLM routing decision for gateway chat."""

    action: Literal["direct_answer", "rag_qa", "workflow"] = Field(...)
    reason: str = Field(...)
    answer: str | None = Field(default=None)
    rewritten_query: str | None = Field(default=None)
    workflow_message: str | None = Field(default=None)
    region: str | None = Field(default=None)
    crop_type: str | None = Field(default=None)
    task_type: str | None = Field(default=None)
    need_training: bool | None = Field(default=None)
    need_rag: bool | None = Field(default=None)
    need_report: bool | None = Field(default=None)
    need_confidence: bool | None = Field(default=None)
    normalized_message: str | None = Field(default=None)

    @model_validator(mode="after")
    def _validate_answer_for_direct_mode(self) -> "_AgentRouteDecision":
        if self.action == "direct_answer" and not (self.answer or "").strip():
            raise ValueError("answer is required when action=direct_answer")
        return self


@dataclass(frozen=True)
class _BranchResult:
    """Intermediate response plus persisted conversation payload."""

    response: ChatResponse
    turn: ConversationTurn


class ChatService:
    """Route chat requests through agent, QA retrieval, or workflow execution."""

    def __init__(
        self,
        *,
        orchestrator_client: LocalOrchestratorClient,
        rag_client: LocalRAGServiceClient | None = None,
        llm_provider: AgentLLMProvider | None = None,
        conversation_store: ConversationStore | None = None,
        history_limit: int = 6,
        chat_runtime_adapter: ChatRuntimeAdapter | None = None,
        agent_runtime_enabled: bool = False,
        agent_shadow_compare_enabled: bool = False,
        agent_legacy_fallback_enabled: bool = True,
    ) -> None:
        self._orchestrator_client = orchestrator_client
        self._rag_client = rag_client or LocalRAGServiceClient()
        self._llm_provider = llm_provider
        self._conversation_store = conversation_store
        self._history_limit = history_limit
        self._chat_runtime_adapter = chat_runtime_adapter or ChatRuntimeAdapter()
        self._agent_runtime_enabled = agent_runtime_enabled
        self._agent_shadow_compare_enabled = agent_shadow_compare_enabled
        self._agent_legacy_fallback_enabled = agent_legacy_fallback_enabled

    def handle_chat(self, request: ChatRequest) -> ChatResponse:
        """Process a unified chat request with automatic mode detection."""
        request_id = request.request_id or str(uuid4())
        conversation_id = request.conversation_id or str(uuid4())
        user_id = (request.user_id or "anonymous").strip() or "anonymous"
        logger.info(
            "chat_request_started | request_id=%s | user_id=%s | conversation_id=%s | mode=%s | has_image_path=%s | task_type=%s",
            request_id,
            user_id,
            conversation_id,
            request.mode,
            bool(request.image_path),
            request.task_type,
        )

        try:
            history = self._get_history(user_id=user_id, conversation_id=conversation_id)
        except ConversationStoreError as exc:
            logger.exception(
                "chat_request_history_load_failed | request_id=%s | user_id=%s | conversation_id=%s",
                request_id,
                user_id,
                conversation_id,
            )
            return self._conversation_error_response(
                request_id=request_id,
                user_id=user_id,
                conversation_id=conversation_id,
                request=request,
                detail=f"会话上下文读取失败：{exc}",
            )

        last_turn = history[-1] if history else None
        resolved_mode, route_reason = self._resolve_mode(request=request, last_turn=last_turn)
        if resolved_mode == "agent":
            branch = self._handle_agent(
                request_id=request_id,
                user_id=user_id,
                conversation_id=conversation_id,
                request=request,
                route_reason=route_reason,
                history=history,
                last_turn=last_turn,
            )
        elif resolved_mode == "qa":
            branch = self._handle_qa(
                request_id=request_id,
                user_id=user_id,
                conversation_id=conversation_id,
                request=request,
                route_reason=route_reason,
                history=history,
                last_turn=last_turn,
            )
        else:
            branch = self._handle_workflow(
                request_id=request_id,
                user_id=user_id,
                conversation_id=conversation_id,
                request=request,
                route_reason=route_reason,
                history=history,
                last_turn=last_turn,
            )

        try:
            self._append_turn(branch.turn)
        except ConversationStoreError as exc:
            logger.exception(
                "chat_request_history_append_failed | request_id=%s | user_id=%s | conversation_id=%s",
                request_id,
                user_id,
                conversation_id,
            )
            response = branch.response.model_copy(
                update={
                    "success": False,
                    "message": f"会话上下文保存失败：{exc}",
                    "answer": f"{branch.response.answer}\n\n注意：会话上下文保存失败，后续追问将无法自动继承本轮内容。",
                }
            )
        else:
            response = branch.response

        logger.info(
            "chat_request_completed | request_id=%s | conversation_id=%s | mode=%s | success=%s",
            request_id,
            conversation_id,
            response.mode,
            response.success,
        )
        return response

    def _handle_agent(
        self,
        *,
        request_id: str,
        user_id: str,
        conversation_id: str,
        request: ChatRequest,
        route_reason: str,
        history: list[ConversationTurn],
        last_turn: ConversationTurn | None,
    ) -> _BranchResult:
        if self._agent_runtime_enabled:
            try:
                runtime_branch = self._handle_agent_via_runtime(
                    request_id=request_id,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    request=request,
                    route_reason=route_reason,
                    history=history,
                )
                return self._maybe_attach_shadow_compare(
                    branch=runtime_branch,
                    request_id=request_id,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    request=request,
                    route_reason=route_reason,
                    history=history,
                    last_turn=last_turn,
                )
            except Exception as exc:
                logger.exception(
                    "chat_agent_runtime_failed | request_id=%s | conversation_id=%s",
                    request_id,
                    conversation_id,
                )
                route_reason = f"{route_reason}:runtime_fallback"
                if not self._agent_legacy_fallback_enabled:
                    detail = f"chat runtime 执行失败，且当前已禁用 legacy agent emergency fallback：{exc}"
                    response = ChatResponse(
                        request_id=request_id,
                        conversation_id=conversation_id,
                        user_id=user_id,
                        success=False,
                        mode="agent",
                        route_reason=f"{route_reason}:legacy_disabled",
                        answer=detail,
                        message=detail,
                        history_turn_count=len(history),
                        sources=[],
                    )
                    return _BranchResult(
                        response=response,
                        turn=self._build_turn(
                            response=response,
                            request=request,
                            user_id=user_id,
                            mode="agent",
                            context={
                                "history_turn_count": len(history),
                                "agent_status": "runtime_failed",
                                "detail": str(exc),
                                "agent_audit": {
                                    "path": "runtime_first",
                                    "runtime_status": "failed",
                                    "legacy_fallback_enabled": False,
                                },
                            },
                            sources=[],
                            region=request.region,
                            crop_type=request.crop_type,
                            task_type=request.task_type,
                            image_path=request.image_path,
                            use_mock=request.use_mock,
                        ),
                    )
                if self._llm_provider is None:
                    detail = f"chat runtime 执行失败，且当前未配置 legacy agent fallback：{exc}"
                    response = ChatResponse(
                        request_id=request_id,
                        conversation_id=conversation_id,
                        user_id=user_id,
                        success=False,
                        mode="agent",
                        route_reason=f"{route_reason}:runtime_failed",
                        answer=detail,
                        message=detail,
                        history_turn_count=len(history),
                        sources=[],
                    )
                    return _BranchResult(
                        response=response,
                        turn=self._build_turn(
                            response=response,
                            request=request,
                            user_id=user_id,
                            mode="agent",
                            context={
                                "history_turn_count": len(history),
                                "agent_status": "runtime_failed",
                                "detail": str(exc),
                                "agent_audit": {
                                    "path": "runtime_first",
                                    "runtime_status": "failed",
                                    "legacy_fallback_enabled": True,
                                    "legacy_fallback_available": False,
                                },
                            },
                            sources=[],
                            region=request.region,
                            crop_type=request.crop_type,
                            task_type=request.task_type,
                            image_path=request.image_path,
                            use_mock=request.use_mock,
                        ),
                    )
                legacy_branch = self._handle_agent_via_legacy_router(
                    request_id=request_id,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    request=request,
                    route_reason=route_reason,
                    history=history,
                    last_turn=last_turn,
                )
                return self._with_legacy_fallback_audit(legacy_branch, runtime_error=str(exc))

        return self._handle_agent_via_legacy_router(
            request_id=request_id,
            user_id=user_id,
            conversation_id=conversation_id,
            request=request,
            route_reason=route_reason,
            history=history,
            last_turn=last_turn,
        )

    def _handle_agent_via_legacy_router(
        self,
        *,
        request_id: str,
        user_id: str,
        conversation_id: str,
        request: ChatRequest,
        route_reason: str,
        history: list[ConversationTurn],
        last_turn: ConversationTurn | None,
    ) -> _BranchResult:
        if self._llm_provider is None:
            detail = "当前未配置可用的大模型自调度能力，请配置 Qwen provider 或显式指定 qa/workflow。"
            response = ChatResponse(
                request_id=request_id,
                conversation_id=conversation_id,
                user_id=user_id,
                success=False,
                mode="agent",
                route_reason=route_reason,
                answer=detail,
                message=detail,
                history_turn_count=len(history),
                sources=[],
            )
            return _BranchResult(
                response=response,
                turn=self._build_turn(
                    response=response,
                    request=request,
                    user_id=user_id,
                    mode="agent",
                    context={
                        "history_turn_count": len(history),
                        "agent_status": "unavailable",
                    },
                    sources=[],
                    region=request.region,
                    crop_type=request.crop_type,
                    task_type=request.task_type,
                    image_path=request.image_path,
                    use_mock=request.use_mock,
                ),
            )

        history_summary = self._render_history(history)
        try:
            decision = self._llm_provider.generate_structured(
                system_prompt=(
                    "你是 API Gateway 的统一聊天总控代理。"
                    "你必须一次性完成两件事："
                    "第一，判断当前请求应该如何处理：direct_answer、rag_qa、workflow；"
                    "第二，尽量抽取并规范化 region、crop_type、task_type。"
                    "task_type 只能使用以下规范值之一："
                    "crop_health_detection、yield_estimation、lai_inversion、land_cover_analysis、baldness_detection。"
                    "region 请尽量输出 registry key，例如 河北->hebei、河南->henan、黑龙江->heilongjiang。"
                    "crop_type 请尽量输出 registry key，例如 小麦->wheat、水稻->rice、玉米->maize。"
                    "对于像“NDVI 和 EVI 有什么区别”这类通用知识问答，优先选择 direct_answer。"
                    "只有当用户明确需要图像分析、检测/识别/分割/反演、模型调用、报告、置信度、可视化，"
                    "或者明显需要工具执行时，才选择 workflow。"
                    "当用户明确要求基于知识库/资料/来源回答，或问题依赖本地知识库时，选择 rag_qa。"
                    "信息不足时不要编造，字段可以为 null。"
                ),
                user_prompt=(
                    f"当前用户消息：\n{request.message}\n\n"
                    "对话历史：\n"
                    f"{history_summary or '无'}\n\n"
                    "当前显式元数据（JSON）：\n"
                    f"{json.dumps({'region': request.region, 'crop_type': request.crop_type, 'task_type': request.task_type, 'image_path': request.image_path, 'use_mock': request.use_mock, 'top_k': request.top_k, 'extra_params': request.extra_params}, ensure_ascii=False, sort_keys=True)}\n\n"
                    "请给出调度决定。"
                ),
                response_model=_AgentRouteDecision,
            )
        except AgentLLMError as exc:
            logger.warning("chat_agent_routing_failed | request_id=%s | detail=%s", request_id, str(exc))
            if request.mode == "agent":
                detail = f"大模型自调度失败：{exc}"
                response = ChatResponse(
                    request_id=request_id,
                    conversation_id=conversation_id,
                    user_id=user_id,
                    success=False,
                    mode="agent",
                    route_reason="explicit:agent_failed",
                    answer=detail,
                    message=detail,
                    history_turn_count=len(history),
                    sources=[],
                )
                return _BranchResult(
                    response=response,
                    turn=self._build_turn(
                        response=response,
                        request=request,
                        user_id=user_id,
                        mode="agent",
                        context={
                            "history_turn_count": len(history),
                            "agent_status": "failed",
                            "detail": str(exc),
                        },
                        sources=[],
                        region=request.region,
                        crop_type=request.crop_type,
                        task_type=request.task_type,
                        image_path=request.image_path,
                        use_mock=request.use_mock,
                    ),
                )

            fallback_mode, fallback_reason = self._resolve_mode_legacy(
                request=request,
                last_turn=last_turn,
            )
            if fallback_mode == "qa":
                return self._handle_qa(
                    request_id=request_id,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    request=request,
                    route_reason=f"{fallback_reason}|fallback_from_agent",
                    history=history,
                    last_turn=last_turn,
                )
            return self._handle_workflow(
                request_id=request_id,
                user_id=user_id,
                conversation_id=conversation_id,
                request=request,
                route_reason=f"{fallback_reason}|fallback_from_agent",
                history=history,
                last_turn=last_turn,
            )

        resolved_region = self._resolve_region(request=request, decision=decision)
        resolved_crop_type = self._resolve_crop_type(request=request, decision=decision)
        resolved_task_type = self._resolve_task_type(request=request, decision=decision)
        agent_plan = self._build_agent_plan_context(
            decision=decision,
            region=resolved_region,
            crop_type=resolved_crop_type,
            task_type=resolved_task_type,
        )

        if decision.action == "direct_answer":
            response = ChatResponse(
                request_id=request_id,
                conversation_id=conversation_id,
                user_id=user_id,
                success=True,
                mode="agent",
                route_reason=f"{route_reason}:direct_answer",
                answer=(decision.answer or "").strip(),
                message="chat completed",
                history_turn_count=len(history),
                sources=[],
            )
            return _BranchResult(
                response=response,
                turn=self._build_turn(
                    response=response,
                    request=request,
                    user_id=user_id,
                    mode="agent",
                    context={
                        "history_turn_count": len(history),
                        "agent_action": decision.action,
                        "agent_reason": decision.reason,
                        "agent_plan": agent_plan,
                    },
                    sources=[],
                    region=resolved_region,
                    crop_type=resolved_crop_type,
                    task_type=resolved_task_type,
                    image_path=request.image_path,
                    use_mock=request.use_mock,
                ),
            )

        if decision.action == "rag_qa":
            effective_request = request.model_copy(
                update={
                    "region": resolved_region,
                    "crop_type": resolved_crop_type,
                    "task_type": resolved_task_type,
                    "extra_params": {
                        **request.extra_params,
                        "agent_plan": agent_plan,
                    },
                },
                deep=True,
            )
            return self._handle_qa(
                request_id=request_id,
                user_id=user_id,
                conversation_id=conversation_id,
                request=effective_request,
                route_reason=f"{route_reason}:rag_qa:{decision.reason}",
                history=history,
                last_turn=last_turn,
                forced_query=(decision.rewritten_query or "").strip() or None,
            )

        effective_request = request.model_copy(
            update={
                "message": (
                    (decision.normalized_message or decision.workflow_message or request.message).strip()
                    or request.message
                ),
                "region": resolved_region,
                "crop_type": resolved_crop_type,
                "task_type": resolved_task_type,
                "extra_params": {
                    **request.extra_params,
                    "agent_plan": agent_plan,
                },
            },
            deep=True,
        )
        return self._handle_workflow(
            request_id=request_id,
            user_id=user_id,
            conversation_id=conversation_id,
            request=effective_request,
            route_reason=f"{route_reason}:workflow:{decision.reason}",
            history=history,
            last_turn=last_turn,
        )

    def _maybe_attach_shadow_compare(
        self,
        *,
        branch: _BranchResult,
        request_id: str,
        user_id: str,
        conversation_id: str,
        request: ChatRequest,
        route_reason: str,
        history: list[ConversationTurn],
        last_turn: ConversationTurn | None,
    ) -> _BranchResult:
        if not self._agent_shadow_compare_enabled:
            return branch

        if self._llm_provider is None:
            merged_context = {
                **branch.turn.context,
                "shadow_compare": {
                    "enabled": True,
                    "status": "skipped",
                    "reason": "legacy_llm_unavailable",
                },
            }
        else:
            try:
                shadow_branch = self._handle_agent_via_legacy_router(
                    request_id=request_id,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    request=request,
                    route_reason=f"{route_reason}:shadow_compare",
                    history=history,
                    last_turn=last_turn,
                )
                merged_context = {
                    **branch.turn.context,
                    "shadow_compare": {
                        "enabled": True,
                        "status": "completed",
                        "primary_mode": branch.response.mode,
                        "primary_route_reason": branch.response.route_reason,
                        "primary_success": branch.response.success,
                        "mode": shadow_branch.response.mode,
                        "route_reason": shadow_branch.response.route_reason,
                        "success": shadow_branch.response.success,
                        "comparison": {
                            "mode_match": branch.response.mode == shadow_branch.response.mode,
                            "success_match": branch.response.success == shadow_branch.response.success,
                            "route_reason_match": branch.response.route_reason == shadow_branch.response.route_reason,
                        },
                    },
                }
            except Exception as exc:
                logger.exception(
                    "chat_agent_shadow_compare_failed | request_id=%s | conversation_id=%s",
                    request_id,
                    conversation_id,
                )
                merged_context = {
                    **branch.turn.context,
                    "shadow_compare": {
                        "enabled": True,
                        "status": "failed",
                        "detail": str(exc),
                    },
                }

        turn = self._build_turn(
            response=branch.response,
            request=request,
            user_id=user_id,
            mode=branch.response.mode,
            context=self._with_shadow_compare_audit(merged_context),
            sources=branch.turn.sources,
            region=branch.turn.region,
            crop_type=branch.turn.crop_type,
            task_type=branch.turn.task_type,
            image_path=branch.turn.image_path,
            use_mock=branch.turn.use_mock,
            workflow_status=branch.turn.workflow_status,
        )
        return _BranchResult(response=branch.response, turn=turn)

    def _handle_agent_via_runtime(
        self,
        *,
        request_id: str,
        user_id: str,
        conversation_id: str,
        request: ChatRequest,
        route_reason: str,
        history: list[ConversationTurn],
    ) -> _BranchResult:
        runtime_result = self._chat_runtime_adapter.run(
            request_id=request_id,
            user_id=user_id,
            conversation_id=conversation_id,
            request=request,
            history=history,
        )
        response = ChatResponse(
            request_id=request_id,
            conversation_id=conversation_id,
            user_id=user_id,
            success=runtime_result.success,
            mode=runtime_result.response_mode,
            route_reason=f"{route_reason}:{runtime_result.route_reason_suffix}",
            answer=runtime_result.answer,
            message="chat completed" if runtime_result.success else runtime_result.answer,
            history_turn_count=len(history),
            workflow_status=runtime_result.workflow_status,
            inference_result=runtime_result.inference_result,
            rag_result=runtime_result.rag_result,
            report_result=runtime_result.report_result,
            confidence_result=runtime_result.confidence_result,
            visualization_result=runtime_result.visualization_result,
            sources=runtime_result.sources,
        )
        return _BranchResult(
            response=response,
            turn=self._build_turn(
                response=response,
                request=request,
                user_id=user_id,
                mode=runtime_result.response_mode,
                context=self._with_runtime_audit(
                    runtime_result.context,
                    final_mode=runtime_result.final_mode,
                    response_mode=runtime_result.response_mode,
                ),
                sources=runtime_result.sources,
                region=runtime_result.region,
                crop_type=runtime_result.crop_type,
                task_type=runtime_result.task_type,
                image_path=request.image_path,
                use_mock=request.use_mock,
                workflow_status=runtime_result.workflow_status,
            ),
        )

    @staticmethod
    def _with_runtime_audit(
        context: dict[str, Any],
        *,
        final_mode: str,
        response_mode: str,
    ) -> dict[str, Any]:
        audit = {
            "path": "runtime_first",
            "runtime_runner": context.get("runtime_runner"),
            "runtime_status": context.get("chat_runtime_status"),
            "final_mode": final_mode,
            "response_mode": response_mode,
            "replan_count": context.get("replan_count"),
            "max_replans": context.get("max_replans"),
            "shadow_compare_enabled": False,
        }
        return {
            **context,
            "agent_audit": audit,
        }

    @staticmethod
    def _with_legacy_fallback_audit(branch: _BranchResult, *, runtime_error: str) -> _BranchResult:
        context = {
            **branch.turn.context,
            "agent_audit": {
                "path": "legacy_fallback",
                "runtime_status": "failed",
                "legacy_fallback_enabled": True,
                "legacy_fallback_used": True,
                "runtime_error": runtime_error,
            },
        }
        turn = ConversationTurn(
            user_id=branch.turn.user_id,
            conversation_id=branch.turn.conversation_id,
            request_id=branch.turn.request_id,
            created_at=branch.turn.created_at,
            mode=branch.turn.mode,
            route_reason=branch.turn.route_reason,
            success=branch.turn.success,
            user_message=branch.turn.user_message,
            answer=branch.turn.answer,
            region=branch.turn.region,
            crop_type=branch.turn.crop_type,
            task_type=branch.turn.task_type,
            image_path=branch.turn.image_path,
            use_mock=branch.turn.use_mock,
            workflow_status=branch.turn.workflow_status,
            sources=branch.turn.sources,
            extra_params=branch.turn.extra_params,
            context=context,
            response_payload=branch.turn.response_payload,
        )
        return _BranchResult(response=branch.response, turn=turn)

    @staticmethod
    def _with_shadow_compare_audit(context: dict[str, Any]) -> dict[str, Any]:
        shadow_compare = context.get("shadow_compare") or {}
        existing_audit = dict(context.get("agent_audit") or {})
        comparison = shadow_compare.get("comparison") or {}
        audit = {
            **existing_audit,
            "shadow_compare_enabled": bool(shadow_compare.get("enabled")),
            "shadow_compare_status": shadow_compare.get("status"),
            "shadow_compare_mode_match": comparison.get("mode_match"),
            "shadow_compare_success_match": comparison.get("success_match"),
            "shadow_compare_route_reason_match": comparison.get("route_reason_match"),
        }
        return {
            **context,
            "agent_audit": audit,
        }

    def _handle_qa(
        self,
        *,
        request_id: str,
        user_id: str,
        conversation_id: str,
        request: ChatRequest,
        route_reason: str,
        history: list[ConversationTurn],
        last_turn: ConversationTurn | None,
        forced_query: str | None = None,
    ) -> _BranchResult:
        effective_query = forced_query or self._build_qa_query(
            message=request.message,
            last_turn=last_turn,
        )
        qa_context = self._build_qa_context(
            request=request,
            history=history,
            last_turn=last_turn,
            effective_query=effective_query,
            conversation_id=conversation_id,
        )
        try:
            rag_result = self._rag_client.run_rag(
                request_id=request_id,
                user_query=effective_query,
                task_type=request.task_type,
                region=request.region,
                crop_type=request.crop_type,
                context=qa_context,
                top_k=request.top_k,
            )
        except RAGServiceClientError as exc:
            logger.warning("chat_qa_failed | request_id=%s | detail=%s", request_id, str(exc))
            detail = f"知识问答检索失败：{exc}"
            response = ChatResponse(
                request_id=request_id,
                conversation_id=conversation_id,
                user_id=user_id,
                success=False,
                mode="qa",
                route_reason=route_reason,
                answer=detail,
                message=str(exc),
                history_turn_count=len(history),
                rag_result=None,
                sources=[],
            )
            return _BranchResult(
                response=response,
                turn=self._build_turn(
                    response=response,
                    request=request,
                    user_id=user_id,
                    mode="qa",
                    context={
                        "effective_query": effective_query,
                        "history_turn_count": len(history),
                    },
                    sources=[],
                    region=request.region,
                    crop_type=request.crop_type,
                    task_type=request.task_type,
                    image_path=request.image_path,
                    use_mock=request.use_mock,
                ),
            )

        history_summary = self._render_history(history)
        answer = self._build_qa_answer(
            question=request.message,
            effective_query=effective_query,
            history_summary=history_summary,
            rag_result=rag_result,
        )
        response = ChatResponse(
            request_id=request_id,
            conversation_id=conversation_id,
            user_id=user_id,
            success=True,
            mode="qa",
            route_reason=route_reason,
            answer=answer,
            message="chat completed",
            history_turn_count=len(history),
            rag_result=rag_result.model_dump(),
            sources=list(rag_result.sources),
        )
        return _BranchResult(
            response=response,
            turn=self._build_turn(
                response=response,
                request=request,
                user_id=user_id,
                mode="qa",
                context={
                    "effective_query": effective_query,
                    "history_turn_count": len(history),
                    "history_summary": history_summary,
                },
                sources=list(rag_result.sources),
                region=request.region,
                crop_type=request.crop_type,
                task_type=request.task_type,
                image_path=request.image_path,
                use_mock=request.use_mock,
            ),
        )

    def _handle_workflow(
        self,
        *,
        request_id: str,
        user_id: str,
        conversation_id: str,
        request: ChatRequest,
        route_reason: str,
        history: list[ConversationTurn],
        last_turn: ConversationTurn | None,
    ) -> _BranchResult:
        effective_request, inherited_fields = self._inherit_workflow_fields(
            request=request,
            last_turn=last_turn,
            conversation_id=conversation_id,
            history=history,
        )
        workflow_extra_params = dict(effective_request.extra_params)
        workflow_extra_params["conversation_id"] = conversation_id
        workflow_extra_params["conversation_history"] = self._render_history(history)
        if inherited_fields:
            workflow_extra_params["inherited_fields"] = inherited_fields

        try:
            workflow_response = self._orchestrator_client.run_workflow(
                WorkflowRequest(
                    request_id=request_id,
                    user_query=effective_request.message,
                    region=effective_request.region,
                    crop_type=effective_request.crop_type,
                    task_type=effective_request.task_type,
                    image_path=effective_request.image_path,
                    use_mock=effective_request.use_mock,
                    extra_params=workflow_extra_params,
                )
            )
        except OrchestratorClientError as exc:
            logger.warning("chat_workflow_failed | request_id=%s | detail=%s", request_id, str(exc))
            detail = f"工作流执行失败：{exc}"
            response = ChatResponse(
                request_id=request_id,
                conversation_id=conversation_id,
                user_id=user_id,
                success=False,
                mode="workflow",
                route_reason=route_reason,
                answer=detail,
                message=str(exc),
                history_turn_count=len(history),
                workflow_status="failed",
                sources=[],
            )
            return _BranchResult(
                response=response,
                turn=self._build_turn(
                    response=response,
                    request=request,
                    user_id=user_id,
                    mode="workflow",
                    context={
                        "history_turn_count": len(history),
                        "inherited_fields": inherited_fields,
                        "message_inherited": effective_request.message != request.message,
                    },
                    sources=[],
                    region=effective_request.region,
                    crop_type=effective_request.crop_type,
                    task_type=effective_request.task_type,
                    image_path=effective_request.image_path,
                    use_mock=effective_request.use_mock,
                ),
            )

        final_state = workflow_response.final_state
        answer = self._build_workflow_answer(
            workflow_status=workflow_response.status,
            final_state=final_state,
        )
        rag_result = final_state.get("rag_result")
        sources = self._extract_sources(rag_result)
        response = ChatResponse(
            request_id=workflow_response.request_id,
            conversation_id=conversation_id,
            user_id=user_id,
            success=workflow_response.status == "completed",
            mode="workflow",
            route_reason=route_reason,
            answer=answer,
            message="chat completed"
            if workflow_response.status == "completed"
            else workflow_response.status,
            history_turn_count=len(history),
            workflow_status=workflow_response.status,
            inference_result=final_state.get("inference_result"),
            rag_result=rag_result,
            report_result=final_state.get("report_result"),
            confidence_result=final_state.get("confidence_result"),
            visualization_result=final_state.get("visualization_result"),
            sources=sources,
        )
        return _BranchResult(
            response=response,
            turn=self._build_turn(
                response=response,
                request=request,
                user_id=user_id,
                mode="workflow",
                context={
                    "history_turn_count": len(history),
                    "inherited_fields": inherited_fields,
                    "message_inherited": effective_request.message != request.message,
                },
                sources=sources,
                region=effective_request.region,
                crop_type=effective_request.crop_type,
                task_type=effective_request.task_type,
                image_path=effective_request.image_path,
                use_mock=effective_request.use_mock,
                workflow_status=workflow_response.status,
            ),
        )

    def _resolve_mode(
        self,
        *,
        request: ChatRequest,
        last_turn: ConversationTurn | None,
    ) -> tuple[ResolvedMode, str]:
        if request.mode == "agent":
            return "agent", "explicit:agent"
        if request.mode == "qa":
            return "qa", "explicit:qa"
        if request.mode == "workflow":
            return "workflow", "explicit:workflow"
        if self._agent_runtime_enabled:
            return "agent", "auto:agent_runtime"
        if self._llm_provider is not None:
            return "agent", "auto:agent_llm"

        fallback_mode, fallback_reason = self._resolve_mode_legacy(
            request=request,
            last_turn=last_turn,
        )
        return fallback_mode, fallback_reason

    def _resolve_mode_legacy(
        self,
        *,
        request: ChatRequest,
        last_turn: ConversationTurn | None,
    ) -> tuple[Literal["qa", "workflow"], str]:

        message = request.message.strip().lower()
        if request.image_path or request.task_type or request.use_mock is not None:
            return "workflow", "auto:workflow_due_to_explicit_workflow_metadata"
        if self._contains_any(message, _AUTO_WORKFLOW_IMAGE_KEYWORDS):
            return "workflow", "auto:workflow_due_to_image_reference"
        if self._contains_any(message, _AUTO_WORKFLOW_IMPERATIVE_KEYWORDS):
            return "workflow", "auto:workflow_due_to_imperative_task_request"
        if self._contains_any(message, _AUTO_WORKFLOW_OUTPUT_KEYWORDS):
            return "workflow", "auto:workflow_due_to_requested_outputs"
        if self._contains_any(message, _AUTO_WORKFLOW_TASK_KEYWORDS):
            return "workflow", "auto:workflow_due_to_task_keyword"
        if self._contains_any(message, _AUTO_QA_KNOWLEDGE_KEYWORDS):
            return "qa", "auto:qa_due_to_knowledge_question"
        if last_turn is not None and self._is_follow_up_message(message):
            if last_turn.mode == "workflow":
                return "workflow", "auto:inherited_workflow_from_conversation"
            return "qa", "auto:inherited_qa_from_conversation"
        if "?" in message or "？" in message:
            return "qa", "auto:qa_due_to_question_pattern"
        return "qa", "auto:qa_default"

    def _build_qa_answer(
        self,
        *,
        question: str,
        effective_query: str,
        history_summary: str,
        rag_result: RagServiceResult,
    ) -> str:
        llm_answer = self._build_llm_qa_answer(
            question=question,
            effective_query=effective_query,
            history_summary=history_summary,
            rag_result=rag_result,
        )
        if llm_answer:
            return llm_answer

        if not rag_result.results:
            return "当前知识库中没有检索到与该问题直接相关的内容。"

        snippets = []
        for index, result in enumerate(rag_result.results[:3], start=1):
            text = str(result.get("text", "")).strip()
            if not text:
                continue
            snippets.append(f"{index}. {text}")
        if not snippets:
            return "当前知识库中检索到了候选条目，但没有可直接整理的内容。"
        return "根据当前知识库检索结果，整理到以下相关片段：\n" + "\n".join(snippets)

    def _build_llm_qa_answer(
        self,
        *,
        question: str,
        effective_query: str,
        history_summary: str,
        rag_result: RagServiceResult,
    ) -> str | None:
        if self._llm_provider is None or not rag_result.results:
            return None

        snippets = [
            {
                "source": result.get("source"),
                "text": result.get("text"),
                "score": result.get("score"),
            }
            for result in rag_result.results[:3]
        ]
        try:
            answer = self._llm_provider.generate_text(
                system_prompt=(
                    "你是遥感知识问答助手。请严格基于给定检索片段，用中文给出简洁准确的回答。"
                    "如果证据不足，要明确说明。不要编造知识。"
                ),
                user_prompt=(
                    f"当前用户问题：\n{question}\n\n"
                    f"用于检索的扩展查询：\n{effective_query}\n\n"
                    "对话历史摘要：\n"
                    f"{history_summary or '无'}\n\n"
                    "检索片段（JSON）：\n"
                    f"{json.dumps(snippets, ensure_ascii=False, sort_keys=True)}\n\n"
                    "请直接输出最终回答。"
                ),
            ).strip()
        except AgentLLMError as exc:
            logger.warning("chat_qa_llm_fallback | detail=%s", str(exc))
            return None
        return answer or None

    def _build_workflow_answer(
        self,
        *,
        workflow_status: str,
        final_state: dict[str, Any],
    ) -> str:
        if workflow_status != "completed":
            return f"工作流未成功完成，当前状态为：{workflow_status}。"

        lines: list[str] = ["已按任务工作流完成处理。"]
        task_type = final_state.get("task_type")
        region = final_state.get("region")
        crop_type = final_state.get("crop_type")
        summary_bits = []
        if task_type:
            summary_bits.append(f"任务：{task_type}")
        if region:
            summary_bits.append(f"区域：{region}")
        if crop_type:
            summary_bits.append(f"对象：{crop_type}")
        if summary_bits:
            lines.append("；".join(summary_bits) + "。")

        inference_result = final_state.get("inference_result") or {}
        if inference_result:
            confidence = inference_result.get("confidence")
            affected_area = inference_result.get("affected_area")
            inference_bits = []
            if affected_area is not None:
                inference_bits.append(f"影响面积：{affected_area}")
            if confidence is not None:
                inference_bits.append(f"模型置信度：{confidence}")
            if inference_bits:
                lines.append("推理结果摘要：" + "；".join(inference_bits) + "。")

        confidence_result = final_state.get("confidence_result") or {}
        if confidence_result:
            final_label = confidence_result.get("final_label")
            final_confidence = confidence_result.get("final_confidence")
            confidence_bits = []
            if final_label:
                confidence_bits.append(f"综合评级：{final_label}")
            if final_confidence is not None:
                confidence_bits.append(f"综合分数：{final_confidence}")
            if confidence_bits:
                lines.append("置信度评估：" + "；".join(confidence_bits) + "。")

        report_result = final_state.get("report_result") or {}
        if report_result.get("report_uri"):
            lines.append(f"报告已生成：{report_result['report_uri']}。")

        visualization_result = final_state.get("visualization_result") or {}
        if visualization_result.get("visualization_uri"):
            lines.append(f"可视化已生成：{visualization_result['visualization_uri']}。")

        rag_result = final_state.get("rag_result") or {}
        rag_summary = str(rag_result.get("summary", "")).strip()
        if rag_summary and rag_summary != _NO_RAG_RESULT_SUMMARY:
            lines.append(f"知识补充摘要：{rag_summary}")

        return "\n".join(lines)

    def _build_qa_query(
        self,
        *,
        message: str,
        last_turn: ConversationTurn | None,
    ) -> str:
        if last_turn is None or not self._is_follow_up_message(message.lower()):
            return message
        return (
            "请基于上一轮对话继续回答当前追问。\n"
            f"上一轮用户消息：{last_turn.user_message}\n"
            f"上一轮助手回答：{last_turn.answer}\n"
            f"当前追问：{message}"
        )

    def _build_qa_context(
        self,
        *,
        request: ChatRequest,
        history: list[ConversationTurn],
        last_turn: ConversationTurn | None,
        effective_query: str,
        conversation_id: str,
    ) -> dict[str, Any]:
        context = dict(request.extra_params)
        context["conversation_id"] = conversation_id
        context["history_turn_count"] = len(history)
        context["conversation_history"] = self._render_history(history)
        context["effective_query"] = effective_query
        if last_turn is not None:
            context["last_mode"] = last_turn.mode
        return context

    def _inherit_workflow_fields(
        self,
        *,
        request: ChatRequest,
        last_turn: ConversationTurn | None,
        conversation_id: str,
        history: list[ConversationTurn],
    ) -> tuple[ChatRequest, list[str]]:
        effective_request = request.model_copy(deep=True)
        inherited_fields: list[str] = []

        if last_turn is not None and last_turn.mode == "workflow":
            if effective_request.region is None and last_turn.region is not None:
                effective_request.region = last_turn.region
                inherited_fields.append("region")
            if effective_request.crop_type is None and last_turn.crop_type is not None:
                effective_request.crop_type = last_turn.crop_type
                inherited_fields.append("crop_type")
            if effective_request.task_type is None and last_turn.task_type is not None:
                effective_request.task_type = last_turn.task_type
                inherited_fields.append("task_type")
            if effective_request.image_path is None and last_turn.image_path is not None:
                effective_request.image_path = last_turn.image_path
                inherited_fields.append("image_path")
            if effective_request.use_mock is None and last_turn.use_mock is not None:
                effective_request.use_mock = last_turn.use_mock
                inherited_fields.append("use_mock")
            if self._is_follow_up_message(request.message.lower()):
                effective_request.message = (
                    "请基于上一轮任务继续处理当前追问，并默认继承上一轮任务的输出要求。\n"
                    f"上一轮用户消息：{last_turn.user_message}\n"
                    f"当前追问：{request.message}"
                )

        merged_extra_params = dict(effective_request.extra_params)
        merged_extra_params["conversation_id"] = conversation_id
        merged_extra_params["conversation_history"] = self._render_history(history)
        effective_request.extra_params = merged_extra_params
        return effective_request, inherited_fields

    def _resolve_region(
        self,
        *,
        request: ChatRequest,
        decision: _AgentRouteDecision,
    ) -> str | None:
        return (
            normalize_region(request.region)
            or normalize_region(decision.region)
            or detect_region_from_text(decision.normalized_message or decision.workflow_message or request.message)
        )

    def _resolve_crop_type(
        self,
        *,
        request: ChatRequest,
        decision: _AgentRouteDecision,
    ) -> str | None:
        return (
            normalize_crop_type(request.crop_type)
            or normalize_crop_type(decision.crop_type)
            or detect_crop_type_from_text(
                decision.normalized_message or decision.workflow_message or request.message
            )
        )

    def _resolve_task_type(
        self,
        *,
        request: ChatRequest,
        decision: _AgentRouteDecision,
    ) -> str | None:
        return (
            normalize_task_type(request.task_type)
            or normalize_task_type(decision.task_type)
            or detect_task_type_from_text(
                decision.normalized_message or decision.workflow_message or request.message
            )
        )

    @staticmethod
    def _build_agent_plan_context(
        *,
        decision: _AgentRouteDecision,
        region: str | None,
        crop_type: str | None,
        task_type: str | None,
    ) -> dict[str, Any]:
        return {
            "action": decision.action,
            "reason": decision.reason,
            "region": region,
            "crop_type": crop_type,
            "task_type": task_type,
            "need_training": decision.need_training,
            "need_rag": decision.need_rag,
            "need_report": decision.need_report,
            "need_confidence": decision.need_confidence,
        }

    def _build_turn(
        self,
        *,
        response: ChatResponse,
        request: ChatRequest,
        user_id: str,
        mode: ResolvedMode,
        context: dict[str, Any],
        sources: list[str],
        region: str | None,
        crop_type: str | None,
        task_type: str | None,
        image_path: str | None,
        use_mock: bool | None,
        workflow_status: str | None = None,
    ) -> ConversationTurn:
        return ConversationStore.build_turn(
            user_id=user_id,
            conversation_id=response.conversation_id,
            request_id=response.request_id,
            mode=mode,
            route_reason=response.route_reason,
            success=response.success,
            user_message=request.message,
            answer=response.answer,
            region=region,
            crop_type=crop_type,
            task_type=task_type,
            image_path=image_path,
            use_mock=use_mock,
            workflow_status=workflow_status or response.workflow_status,
            sources=sources,
            extra_params=request.extra_params,
            context=context,
            response_payload=response.model_dump(),
        )

    def _get_history(self, *, user_id: str, conversation_id: str) -> list[ConversationTurn]:
        if self._conversation_store is None:
            return []
        return self._conversation_store.get_recent_turns(
            user_id=user_id,
            conversation_id=conversation_id,
            limit=self._history_limit,
        )

    def _append_turn(self, turn: ConversationTurn) -> None:
        if self._conversation_store is None:
            return
        self._conversation_store.append_turn(turn)

    def _conversation_error_response(
        self,
        *,
        request_id: str,
        user_id: str,
        conversation_id: str,
        request: ChatRequest,
        detail: str,
    ) -> ChatResponse:
        mode: ResolvedMode = "workflow" if request.mode == "workflow" else "qa"
        if request.mode == "agent":
            mode = "agent"
        route_reason = "conversation:error"
        return ChatResponse(
            request_id=request_id,
            conversation_id=conversation_id,
            user_id=user_id,
            success=False,
            mode=mode,
            route_reason=route_reason,
            answer=detail,
            message=detail,
            history_turn_count=0,
            sources=[],
        )

    def _render_history(self, history: list[ConversationTurn]) -> str:
        if not history:
            return ""
        lines = []
        for index, turn in enumerate(history, start=1):
            lines.append(
                f"第{index}轮 | 模式：{turn.mode} | 用户：{turn.user_message} | 助手：{turn.answer}"
            )
        return "\n".join(lines)

    @staticmethod
    def _extract_sources(rag_result: dict[str, Any] | None) -> list[str]:
        if not rag_result:
            return []
        raw_sources = rag_result.get("sources", [])
        if not isinstance(raw_sources, list):
            return []
        return [str(source) for source in raw_sources]

    @staticmethod
    def _contains_any(message: str, keywords: tuple[str, ...]) -> bool:
        return any(keyword in message for keyword in keywords)

    def _is_follow_up_message(self, message: str) -> bool:
        normalized = message.strip().lower()
        if not normalized:
            return False
        if self._contains_any(normalized, _FOLLOW_UP_KEYWORDS):
            return True
        return len(normalized) <= 12 and normalized.endswith(("呢", "吗", "么", "?"))
