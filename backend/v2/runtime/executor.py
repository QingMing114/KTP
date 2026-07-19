"""Tool executor for the V2 bounded runtime.

Extracted from BoundedRuntimeEngine — handles single-tool invocation,
KTP pack-flow orchestration, and PROSAIL scene reasoning.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable
from uuid import uuid4

from v2.adapters.python_services.ktp_services import (
    KTP_DEFAULT_CROP_TYPE,
    KTP_DEFAULT_REGION,
    KTP_DEFAULT_TASK_TYPE,
    KtpExecutionContext,
    KtpServiceError,
)
from v2.packs.registry import DomainPackRegistry
from v2.policies.guard import PolicyGuard, PolicyGuardError
from v2.shared.schemas import (
    AssistantMessagePartV2,
    AssistantMessageV2,
    ExecutorActionV2,
    ObservationV2,
    PackArtifactView,
    PermissionResult,
    RunDetail,
    RunEventV2,
    ToolInvocationView,
    TraceEventV2,
)
from v2.tools.handlers import (
    _artifact_from_confidence,
    _artifact_from_inference,
    _artifact_from_model_lookup,
    _artifact_from_report,
    _artifact_from_visualization,
    _context_payload,
)
from v2.tools.registry import ToolRegistryV2

logger = logging.getLogger(__name__)


# ── Free helpers (extracted from engine static methods) ──


def append_assistant_part(run: RunDetail, part: AssistantMessagePartV2) -> None:
    """Append a part to the run's assistant message."""
    if run.assistant_message is None:
        run.assistant_message = AssistantMessageV2(parts=[])
    run.assistant_message.parts.append(part)


def build_pack_step_input(*, context: KtpExecutionContext, step_name: str) -> dict[str, object]:
    """Build tool input dict for a single KTP pack-flow step."""
    payload: dict[str, object] = {
        "query": context.query,
        "region": context.region,
        "crop_type": context.crop_type,
        "task_type": context.task_type,
        "request_id": context.request_id,
        "use_mock_backend": context.use_mock_backend,
        "image_path": context.image_path,
        "top_k": context.top_k,
        "extra_params": dict(context.extra_params),
    }
    if step_name == "ktp.retrieve_knowledge":
        payload["top_k"] = context.top_k
    return payload


def build_ktp_pack_flow_success_message(
    *,
    context: KtpExecutionContext,
    include_knowledge: bool,
    include_visualization: bool,
) -> str:
    """Human-readable success message for a completed KTP pack flow."""
    model_name = (
        context.inference_result.model_name
        if context.inference_result is not None
        else "unknown"
    )
    confidence = (
        f"{context.confidence_result.final_confidence:.2f}"
        if context.confidence_result is not None
        else "n/a"
    )
    knowledge_phrase = (
        "并补充知识依据"
        if include_knowledge and context.rag_result is not None
        else ""
    )
    visualization_phrase = "，同时生成了可视化结果" if include_visualization else ""
    return (
        f"KTP 智能体已完成模型检查、推理、报告和置信度评估"
        f"{knowledge_phrase}{visualization_phrase}。"
        f"当前模型为 {model_name}，最终置信度 {confidence}。"
    )


# ── PROSAIL scene reasoning (pure domain logic) ──


def prosail_scene_reasoning(query: str, image_path: str | None) -> list[tuple[str, str]]:
    """Return list of (label, detail) reasoning steps for PROSAIL scene analysis.

    .. deprecated::
        Import from ``v2.tools.prosail_reasoning`` instead.  This re-export
        is kept for backward compatibility during the Phase A.3 transition.
    """
    from v2.tools.prosail_reasoning import prosail_scene_reasoning as _fn
    return _fn(query, image_path)


# ── ToolExecutor ──


class ToolExecutor:
    """Executes individual tool calls and KTP pack flows.

    Extracted from BoundedRuntimeEngine._execute_single_tool_call /
    _execute_ktp_pack_flow so the engine only handles top-level orchestration.
    """

    def __init__(
        self,
        *,
        tool_registry: ToolRegistryV2,
        policy_guard: PolicyGuard,
        pack_registry: DomainPackRegistry,
    ) -> None:
        self._tool_registry = tool_registry
        self._guard = policy_guard
        self._pack_registry = pack_registry

    # ── Single tool call ──

    def execute_tool_call(
        self,
        *,
        run: RunDetail,
        request_context,
        tool_call,
        visible_tools,
        visible_agents,
        policy,
        event_emitter,
    ) -> dict[str, object]:
        """Execute a single tool call and return a result dict.

        Result keys: ``blocked``, ``observation``, ``final_message``, ``history_item``.

        Mirrors ``BoundedRuntimeEngine._execute_single_tool_call`` exactly.
        """
        spec = self._tool_registry.get_definition(tool_call.tool_name).spec
        invocation = ToolInvocationView(
            call_id=tool_call.call_id or str(uuid4()),
            tool_name=tool_call.tool_name,
            display_name=spec.display_name,
            category=spec.category,
            safety_level=spec.safety_level,
            status="running",
            requires_confirmation=spec.user_confirmation_required,
            tool_input=tool_call.tool_input,
            output_summary="started",
            result_preview="started",
            is_user_visible=spec.surface_visibility in {"all", "web", "api"},
        )
        append_assistant_part(
            run,
            AssistantMessagePartV2(type="tool_call", tool_invocation=invocation),
        )
        event_emitter.emit(
            event="tool.started",
            detail=f"Starting tool {tool_call.tool_name}.",
            tool_invocation=invocation,
        )

        # ── Phase A.2: permission-first check ──
        perm_result = self._guard.check_permission(
            tool_spec=spec,
            policy=policy,
        )
        if self._guard.should_block(perm_result, policy=policy):
            # Hard block: dangerous tools, or approval-required in auto_approve mode
            blocked_invocation = invocation.model_copy(
                update={
                    "status": "blocked",
                    "output_summary": "blocked" if perm_result == PermissionResult.BLOCKED else "approval_required",
                    "result_preview": "blocked" if perm_result == PermissionResult.BLOCKED else "approval_required",
                }
            )
            run.tool_invocations.append(blocked_invocation)
            event_label = "tool.blocked" if perm_result == PermissionResult.BLOCKED else "approval_required"
            run.trace.append(
                TraceEventV2(
                    node="policy_guard",
                    event=event_label,
                    detail=f"Tool {tool_call.tool_name} blocked by policy: {perm_result.value}.",
                )
            )
            observation = ObservationV2(
                source=tool_call.tool_name,
                status="error",
                summary=perm_result.value,
                payload={"tool_name": tool_call.tool_name, "tool_input": tool_call.tool_input},
            )
            append_assistant_part(
                run,
                AssistantMessagePartV2(
                    type="tool_result",
                    tool_invocation=blocked_invocation,
                    text=perm_result.value,
                    status="blocked",
                ),
            )
            event_emitter.emit(
                event="tool.blocked",
                detail=f"Tool {tool_call.tool_name} blocked by policy: {perm_result.value}.",
                observation=observation,
                tool_invocation=blocked_invocation,
            )
            return {
                "blocked": True,
                "observation": observation,
                "final_message": f"Tool {tool_call.tool_name} blocked by policy: {perm_result.value}.",
                "history_item": {
                    "tool_name": tool_call.tool_name,
                    "status": "blocked",
                    "summary": perm_result.value,
                },
            }

        if perm_result == PermissionResult.NEEDS_APPROVAL:
            # require_approval mode — emit event and return awaiting state
            awaiting_invocation = invocation.model_copy(
                update={
                    "status": "awaiting_approval",
                    "output_summary": "awaiting_approval",
                    "result_preview": "awaiting_approval",
                }
            )
            run.tool_invocations.append(awaiting_invocation)
            run.trace.append(
                TraceEventV2(
                    node="policy_guard",
                    event="approval_required",
                    detail=f"Tool {tool_call.tool_name} requires approval before execution.",
                )
            )
            observation = ObservationV2(
                source=tool_call.tool_name,
                status="awaiting_approval",
                summary=f"Tool {tool_call.tool_name} is awaiting user approval.",
                payload={"tool_name": tool_call.tool_name, "tool_input": tool_call.tool_input},
            )
            append_assistant_part(
                run,
                AssistantMessagePartV2(
                    type="tool_result",
                    tool_invocation=awaiting_invocation,
                    text="awaiting_approval",
                    status="awaiting_approval",
                ),
            )
            event_emitter.emit(
                event="submission.approval_required",
                detail=f"Tool {tool_call.tool_name} requires user approval.",
                observation=observation,
                tool_invocation=awaiting_invocation,
                run_status="awaiting_approval",
            )
            return {
                "blocked": True,
                "observation": observation,
                "final_message": f"Tool {tool_call.tool_name} is awaiting user approval.",
                "history_item": {
                    "tool_name": tool_call.tool_name,
                    "status": "awaiting_approval",
                    "summary": "awaiting_approval",
                },
            }

        action = ExecutorActionV2(
            action_type=(
                "run_pack_flow"
                if spec.is_macro and tool_call.tool_name == "ktp.analysis_pipeline"
                else "invoke_tool"
            ),
            tool_name=tool_call.tool_name,
            tool_input=tool_call.tool_input,
            pack_name=spec.pack_name,
            flow_name="analysis_pipeline" if tool_call.tool_name == "ktp.analysis_pipeline" else None,
        )
        macro_invocation_index: int | None = None
        try:
            self._guard.validate_action(
                action=ExecutorActionV2(
                    action_type="invoke_tool",
                    tool_name=tool_call.tool_name,
                    tool_input=tool_call.tool_input,
                ),
                policy=policy,
                visible_tools=visible_tools,
                visible_agents=visible_agents,
                replan_count=0,
                delegation_count=0,
            )
            if action.action_type == "run_pack_flow":
                macro_invocation_index = len(run.tool_invocations)
                run.tool_invocations.append(invocation)
                observation, artifacts, final_message = self.execute_pack_flow(
                    run=run,
                    request_context=request_context,
                    action=action,
                    policy=policy,
                    visible_tools=self._tool_registry.list_tools(),
                    visible_agents=visible_agents,
                    replan_count=0,
                    delegation_count=0,
                    event_emitter=event_emitter,
                )
            elif tool_call.tool_name == "prosail.lai_html_report":
                # Direct sub-tool selection — enrich with PROSAIL reasoning + pixel progress
                tool_input = dict(tool_call.tool_input or {})
                # Use pre-extracted scene parameters if available (LLM-driven, Step 3)
                _scene_params = getattr(request_context, "scene_parameters", None)
                if _scene_params is not None:
                    _constraints = _scene_params.to_constraints()
                    if _constraints:
                        event_emitter.emit(
                            event="prosail.reasoning",
                            detail=(
                                f"使用LLM提取的场景参数（置信度 {_scene_params.confidence:.0%}）\n"
                                f"{_scene_params.reasoning}"
                            ),
                        )
                        tool_input = {**tool_input, "scene_constraints": _constraints}
                else:
                    _image_path = tool_input.get("image_path")
                    _reasoning_text = f"{run.input_message} {tool_input.get('query') or ''}".strip()
                    # Step 2: extract scene constraints from reasoning and inject into tool_input
                    _scene_result = prosail_scene_reasoning(_reasoning_text, _image_path)
                    for _r_label, _r_detail in _scene_result.steps:
                        event_emitter.emit(event="prosail.reasoning", detail=f"{_r_label}\n{_r_detail}")
                    if _scene_result.constraints:
                        tool_input = {**tool_input, "scene_constraints": _scene_result.constraints}

                def _single_progress_sink(current: int, total: int) -> None:
                    event_emitter.emit(
                        event="tool.progress",
                        detail=f"{current}/{total}",
                        tool_progress={
                            "current": current,
                            "total": total,
                            "call_id": invocation.call_id,
                        },
                    )

                from v2.tools.lai_report_handler import run_lai_html_report

                observation, artifacts = run_lai_html_report(
                    progress_callback=_single_progress_sink,
                    **tool_input,
                )
                final_message = observation.summary
            else:
                observation, artifacts = self._tool_registry.invoke(
                    tool_name=tool_call.tool_name,
                    tool_input=tool_call.tool_input,
                )
                final_message = observation.summary
        except PolicyGuardError as exc:
            observation = ObservationV2(
                source=tool_call.tool_name,
                status="error",
                summary=str(exc),
                payload={"tool_name": tool_call.tool_name, "tool_input": tool_call.tool_input},
            )
            artifacts: list[PackArtifactView] = []
            final_message = str(exc)
        except Exception as exc:
            observation = ObservationV2(
                source=tool_call.tool_name,
                status="error",
                summary=str(exc),
                payload={"tool_name": tool_call.tool_name, "tool_input": tool_call.tool_input},
            )
            artifacts = []
            final_message = str(exc)

        completed_invocation = invocation.model_copy(
            update={
                "status": "success" if observation.status == "success" else "error",
                "output_summary": observation.summary,
                "result_preview": observation.summary,
            }
        )
        if macro_invocation_index is not None:
            run.tool_invocations[macro_invocation_index] = completed_invocation
        else:
            run.tool_invocations.append(completed_invocation)
        append_assistant_part(
            run,
            AssistantMessagePartV2(
                type="tool_result",
                tool_invocation=completed_invocation,
                text=observation.summary,
                status=observation.status,
            ),
        )
        run.trace.append(
            TraceEventV2(
                node="tool_dispatch",
                event="tool_finished" if observation.status == "success" else "tool_failed",
                detail=f"Tool {tool_call.tool_name} returned status={observation.status}.",
            )
        )
        event_emitter.emit(
            event="tool.completed",
            detail=f"Tool {tool_call.tool_name} returned status={observation.status}.",
            observation=observation,
            tool_invocation=completed_invocation,
        )

        for artifact in artifacts:
            if artifact not in run.artifacts:
                run.artifacts.append(artifact)
            append_assistant_part(
                run,
                AssistantMessagePartV2(type="artifact", artifact=artifact),
            )
            event_emitter.emit(
                event="artifact.available",
                detail=f"Artifact {artifact.title} is now available.",
                artifact=artifact,
            )

        return {
            "blocked": False,
            "observation": observation,
            "final_message": final_message,
            "history_item": {
                "tool_name": tool_call.tool_name,
                "status": observation.status,
                "summary": observation.summary,
                "artifacts": [a.title for a in artifacts],
            },
        }

    # ── KTP pack flow ──

    def execute_pack_flow(
        self,
        *,
        run: RunDetail,
        request_context,
        action: ExecutorActionV2,
        policy,
        visible_tools,
        visible_agents,
        replan_count: int,
        delegation_count: int,
        event_emitter,
    ) -> tuple[ObservationV2, list[PackArtifactView], str]:
        """Execute a full KTP pack flow (multi-step pipeline).

        Mirrors ``BoundedRuntimeEngine._execute_ktp_pack_flow`` exactly.
        """
        bundle = self._tool_registry.ktp_service_bundle
        if bundle is None:
            observation = ObservationV2(
                source="ktp.pack_flow",
                status="error",
                summary="KTP service bundle is not configured in the active tool registry.",
                payload={"pack_name": action.pack_name, "flow_name": action.flow_name},
            )
            return observation, [], observation.summary

        flow_input = dict(action.tool_input)
        query = str(flow_input.get("query") or run.input_message)
        extra_params = dict(flow_input.get("extra_params") or {})
        include_knowledge = bool(
            flow_input.pop("include_knowledge", False)
            or extra_params.get("include_knowledge")
            or _message_requests_knowledge(query)
        )
        include_visualization = bool(
            flow_input.pop("include_visualization", False)
            or extra_params.get("include_visualization")
            or _message_requests_visualization(query)
        )
        top_k = int(flow_input.pop("top_k", 3) or 3)
        extra_params["include_knowledge"] = include_knowledge
        extra_params["include_visualization"] = include_visualization

        _lai_keywords = {"lai", "leaf area index", "叶面积指数", "叶面积"}
        _baldness_keywords = {"斑秃", "秃斑", "脱发", "baldness", "alopecia"}
        _query_lower = query.lower()
        _is_lai_query = any(kw in _query_lower for kw in _lai_keywords)
        _is_baldness_query = any(kw in _query_lower for kw in _baldness_keywords)
        if _is_lai_query:
            extra_params["task_type"] = "lai_inversion"
        elif _is_baldness_query:
            extra_params["task_type"] = "baldness_detection"
            if not flow_input.get("region"):
                flow_input["region"] = "scalp"
            if not flow_input.get("crop_type"):
                flow_input["crop_type"] = "hair"

        context = bundle.create_context(
            query=query,
            region=str(flow_input.get("region") or extra_params.pop("region", "") or KTP_DEFAULT_REGION),
            crop_type=str(flow_input.get("crop_type") or extra_params.pop("crop_type", "") or KTP_DEFAULT_CROP_TYPE),
            task_type=str(flow_input.get("task_type") or extra_params.pop("task_type", "") or KTP_DEFAULT_TASK_TYPE),
            request_id=str(flow_input.get("request_id") or run.run_id),
            use_mock_backend=bool(flow_input.get("use_mock_backend", False)),
            image_path=str(flow_input.get("image_path")) if flow_input.get("image_path") else None,
            top_k=top_k,
            extra_params=extra_params,
        )

        artifacts: list[PackArtifactView] = []
        step_names = _build_step_names(context=context, include_knowledge=include_knowledge, include_visualization=include_visualization)

        # File-size warning for large images
        if context.image_path:
            try:
                img_size = Path(context.image_path).stat().st_size
                size_mb = img_size / (1024 * 1024)
                if size_mb > 100:
                    event_emitter.send(
                        RunEventV2(
                            sequence=0,
                            event="assistant.status",
                            run_id="",
                            session_id="",
                            detail=f"正在处理大文件（{size_mb:.0f} MB），预计需要较长时间，请耐心等待...",
                        )
                    )
            except OSError:
                pass

        for step_name in step_names:
            # PROSAIL reasoning before LAI report
            if step_name == "prosail.lai_html_report":
                _scene_params = getattr(request_context, "scene_parameters", None)
                if _scene_params is not None:
                    _constraints = _scene_params.to_constraints()
                    if _constraints:
                        event_emitter.emit(
                            event="prosail.reasoning",
                            detail=(
                                f"使用LLM提取的场景参数（置信度 {_scene_params.confidence:.0%}）\n"
                                f"{_scene_params.reasoning}"
                            ),
                        )
                        context.extra_params = dict(context.extra_params or {})
                        context.extra_params["scene_constraints"] = _constraints
                else:
                    _reasoning_text = f"{run.input_message} {query}".strip()
                    _scene_result = prosail_scene_reasoning(_reasoning_text, context.image_path)
                    for r_label, r_detail in _scene_result.steps:
                        event_emitter.emit(event="prosail.reasoning", detail=f"{r_label}\n{r_detail}")
                    # Store constraints in context for _run_ktp_step to forward
                    context.extra_params = dict(context.extra_params or {})
                    context.extra_params["scene_constraints"] = _scene_result.constraints

            step_action = ExecutorActionV2(
                action_type="invoke_tool",
                tool_name=step_name,
                tool_input=build_pack_step_input(context=context, step_name=step_name),
            )
            event_emitter.emit(
                event="tool.started",
                detail=f"开始执行 KTP 流程步骤 {step_name}。",
                tool_invocation=ToolInvocationView(
                    call_id=f"{run.run_id}:{step_name}",
                    tool_name=step_name,
                    display_name=self._tool_registry.get_definition(step_name).spec.display_name,
                    category=self._tool_registry.get_definition(step_name).spec.category,
                    safety_level=self._tool_registry.get_definition(step_name).spec.safety_level,
                    status="running",
                    tool_input=step_action.tool_input,
                    result_preview="started",
                    output_summary="started",
                    is_user_visible=False,
                ),
            )
            try:
                self._guard.validate_action(
                    action=step_action,
                    policy=policy,
                    visible_tools=visible_tools,
                    visible_agents=visible_agents,
                    replan_count=replan_count,
                    delegation_count=delegation_count,
                )
                _call_id = f"{run.run_id}:{step_name}"

                def _make_progress_sink(call_id: str) -> Callable[[int, int], None]:
                    def _sink(current: int, total: int) -> None:
                        event_emitter.emit(
                            event="tool.progress",
                            detail=f"{current}/{total}",
                            tool_progress={"current": current, "total": total, "call_id": call_id},
                        )
                    return _sink

                _progress_sink = _make_progress_sink(_call_id)
                step_observation, step_artifacts = _run_ktp_step(
                    step_name=step_name,
                    context=context,
                    tool_registry=self._tool_registry,
                    progress_sink=_progress_sink,
                )
                artifacts.extend(step_artifacts)
                run.tool_invocations.append(
                    ToolInvocationView(
                        call_id=f"{run.run_id}:{step_name}",
                        tool_name=step_name,
                        display_name=self._tool_registry.get_definition(step_name).spec.display_name,
                        category=self._tool_registry.get_definition(step_name).spec.category,
                        safety_level=self._tool_registry.get_definition(step_name).spec.safety_level,
                        status="success",
                        tool_input=step_action.tool_input,
                        result_preview=step_observation.summary,
                        output_summary=step_observation.summary,
                        is_user_visible=False,
                    )
                )
                run.trace.append(
                    TraceEventV2(
                        node="tool_dispatch",
                        event="tool_finished",
                        detail=f"KTP 流程步骤 {step_name} 执行成功。",
                    )
                )
                event_emitter.emit(
                    event="tool.completed",
                    detail=f"KTP 流程步骤 {step_name} 执行成功。",
                    observation=step_observation,
                    tool_invocation=run.tool_invocations[-1],
                )
                for artifact in step_artifacts:
                    event_emitter.emit(
                        event="artifact.available",
                        detail=f"已输出 {step_name} 的产物。",
                        artifact=artifact,
                    )
                # PROSAIL evaluation summary
                if step_name == "prosail.lai_html_report":
                    _emit_lai_eval(event_emitter, step_observation)
            except Exception as exc:
                error_payload = _context_payload(context)
                error_payload["failed_step"] = step_name
                error_payload["error"] = str(exc)
                run.tool_invocations.append(
                    ToolInvocationView(
                        call_id=f"{run.run_id}:{step_name}",
                        tool_name=step_name,
                        display_name=self._tool_registry.get_definition(step_name).spec.display_name,
                        category=self._tool_registry.get_definition(step_name).spec.category,
                        safety_level=self._tool_registry.get_definition(step_name).spec.safety_level,
                        status="error",
                        tool_input=step_action.tool_input,
                        result_preview=str(exc),
                        output_summary=str(exc),
                        is_user_visible=False,
                    )
                )
                run.trace.append(
                    TraceEventV2(
                        node="tool_dispatch",
                        event="tool_failed",
                        detail=f"KTP 流程步骤 {step_name} 失败: {exc}",
                    )
                )
                event_emitter.emit(
                    event="tool.completed",
                    detail=f"KTP 流程步骤 {step_name} 失败: {exc}",
                    observation=ObservationV2(
                        source="ktp.pack_flow",
                        status="error",
                        summary=f"步骤 {step_name} 失败: {exc}",
                        payload=error_payload,
                    ),
                    tool_invocation=run.tool_invocations[-1],
                )
                if step_name in ("ktp.run_inference_workflow", "ktp.trigger_training"):
                    context.backend_notes.append(f"步骤 {step_name} 失败: {exc}")
                    continue
                observation = ObservationV2(
                    source="ktp.pack_flow",
                    status="error",
                    summary=f"KTP 单智能体流程在步骤 {step_name} 失败: {exc}",
                    payload=error_payload,
                )
                return observation, artifacts, observation.summary

        final_observation = ObservationV2(
            source="ktp.pack_flow",
            status="success",
            summary="KTP 单智能体流程执行完成。",
            payload=_context_payload(context),
        )
        return (
            final_observation,
            artifacts,
            build_ktp_pack_flow_success_message(
                context=context,
                include_knowledge=include_knowledge,
                include_visualization=include_visualization,
            ),
        )


# ── Internal helpers ──


def _build_step_names(
    *,
    context: KtpExecutionContext,
    include_knowledge: bool,
    include_visualization: bool,
) -> list[str]:
    """Determine the ordered list of pack-flow step names."""
    if context.task_type == "lai_inversion":
        if context.image_path:
            return ["prosail.lai_html_report"]
        else:
            return ["ktp.run_inference_workflow", "ktp.build_report", "ktp.evaluate_confidence"]
    elif context.task_type == "yield_estimation":
        return ["apsim.yield_report"]
    else:
        steps = ["ktp.lookup_model_registry", "ktp.run_inference_workflow"]
        if include_knowledge:
            steps.append("ktp.retrieve_knowledge")
        steps.extend(["ktp.build_report", "ktp.evaluate_confidence"])
        if include_visualization:
            steps.append("ktp.build_visualization")
        return steps


def _run_ktp_step(
    *,
    step_name: str,
    context: KtpExecutionContext,
    tool_registry: ToolRegistryV2,
    progress_sink: Callable[[int, int], None] | None = None,
) -> tuple[ObservationV2, list[PackArtifactView]]:
    """Run a single KTP pack-flow step. Mirrors BoundedRuntimeEngine._run_ktp_step."""
    if step_name == "ktp.lookup_model_registry":
        bundle = tool_registry.ktp_service_bundle
        if bundle is None:
            raise KtpServiceError("KTP service bundle not available for model registry lookup")
        result = bundle.ensure_model_lookup(context)
        return (
            ObservationV2(
                source=step_name,
                status="success",
                summary=(
                    f"KTP 模型注册查询完成，model_exists={result.model_exists}，"
                    f"区域={context.region}/{context.crop_type}/{context.task_type}。"
                ),
                payload=_context_payload(context),
            ),
            [
                _artifact_from_model_lookup(
                    result=result,
                    backend=context.model_lookup_backend or "unknown",
                    context=context,
                )
            ],
        )

    if step_name == "prosail.lai_html_report":
        from v2.tools.lai_report_handler import run_lai_html_report

        if not context.image_path:
            raise KtpServiceError("prosail.lai_html_report 需要提供 image_path")
        return run_lai_html_report(
            image_path=context.image_path,
            query=context.query,
            scene_constraints=extra.get("scene_constraints"),
            progress_callback=progress_sink,
        )

    if step_name == "apsim.yield_report":
        from v2.tools.apsim_report_handler import run_apsim_yield_report

        extra = context.extra_params or {}
        return run_apsim_yield_report(
            crop_type=context.crop_type or "wheat",
            region=context.region or "henan",
            start_year=extra.get("start_year"),
            end_year=extra.get("end_year"),
            cultivar=extra.get("cultivar"),
            sowing_date=extra.get("sowing_date"),
            query=context.query,
        )

    bundle = tool_registry.ktp_service_bundle
    if bundle is None:
        raise KtpServiceError("KTP service bundle not available for pack flow execution")

    if step_name == "ktp.run_inference_workflow":
        result = bundle.ensure_inference(context)
        return (
            ObservationV2(
                source=step_name,
                status="success",
                summary=(
                    f"KTP 推理工作流完成，confidence={result.confidence:.2f}，"
                    f"{'LAI' if context.task_type == 'lai_inversion' else 'affected_area'}={result.affected_area:.2f}。"
                ),
                payload=_context_payload(context),
            ),
            [
                _artifact_from_inference(
                    result=result,
                    backend=context.inference_backend or "unknown",
                    task_type=context.task_type,
                )
            ],
        )

    if step_name == "ktp.retrieve_knowledge":
        result = bundle.ensure_knowledge(context)
        return (
            ObservationV2(
                source=step_name,
                status="success",
                summary=(
                    f"KTP 知识检索完成，获取 {len(result.results)} 个片段，"
                    f"{len(result.sources)} 个来源。"
                ),
                payload=_context_payload(context),
            ),
            [],
        )

    if step_name == "ktp.build_report":
        result = bundle.ensure_report(context)
        return (
            ObservationV2(
                source=step_name,
                status="success",
                summary=(
                    f"KTP 报告生成完成，共 {len(result.sections)} 个章节，"
                    f"backend={context.report_backend or 'unknown'}。"
                ),
                payload=_context_payload(context),
            ),
            [
                _artifact_from_report(
                    result=result,
                    backend=context.report_backend or "unknown",
                )
            ],
        )

    if step_name == "ktp.evaluate_confidence":
        result = bundle.ensure_confidence(context)
        return (
            ObservationV2(
                source=step_name,
                status="success",
                summary=(
                    f"KTP 置信度评估完成，final_confidence={result.final_confidence:.2f}，"
                    f"label={result.final_label or 'unknown'}。"
                ),
                payload=_context_payload(context),
            ),
            [
                _artifact_from_confidence(
                    result=result,
                    backend=context.confidence_backend or "unknown",
                )
            ],
        )

    if step_name == "ktp.build_visualization":
        result = bundle.ensure_visualization(context)
        return (
            ObservationV2(
                source=step_name,
                status="success",
                summary=(
                    f"KTP 可视化生成完成，共 {len(result.sections)} 个仪表盘章节，"
                    f"backend={context.visualization_backend or 'unknown'}。"
                ),
                payload=_context_payload(context),
            ),
            [
                _artifact_from_visualization(
                    result=result,
                    backend=context.visualization_backend or "unknown",
                )
            ],
        )

    raise KtpServiceError(f"Unsupported KTP pack flow step: {step_name}")


def _emit_lai_eval(event_emitter, step_observation: ObservationV2) -> None:
    """Emit PROSAIL evaluation summary after LAI report completion."""
    payload = step_observation.payload or {}
    lai_mean = payload.get("lai_mean")
    lai_std = payload.get("lai_std")
    veg_pct = payload.get("vegetation_ratio")
    if isinstance(lai_mean, (int, float)) and isinstance(lai_std, (int, float)) and isinstance(veg_pct, (int, float)):
        conf_str = "较低（建议复查）" if lai_std > 1.0 else "适中" if lai_std > 0.5 else "较高"
        eval_detail = (
            f"反演结果评估\n"
            f"  · 平均 LAI：{float(lai_mean):.3f} m²/m²\n"
            f"  · LAI 标准差：{float(lai_std):.3f}（不确定度{conf_str}）\n"
            f"  · 植被覆盖率：{float(veg_pct):.1f}%\n"
            f"  · HTML 报告已生成并挂载至 /v2/reports/"
        )
    else:
        eval_detail = "反演结果评估\n  · 报告已生成"
    event_emitter.emit(event="prosail.reasoning", detail=eval_detail)


def _message_requests_knowledge(message: str) -> bool:
    normalized = message.lower()
    return any(
        keyword in normalized
        for keyword in ("资料", "来源", "source", "reference", "ndvi", "evi", "explain")
    )


def _message_requests_visualization(message: str) -> bool:
    normalized = message.lower()
    return any(
        keyword in normalized
        for keyword in ("可视化", "dashboard", "visualization", "图", "map")
    )
