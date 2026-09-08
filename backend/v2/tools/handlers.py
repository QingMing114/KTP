from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

# LAI HTML report handler (re-exported for registry convenience)
from v2.tools.lai_report_handler import run_lai_html_report as run_lai_html_report  # noqa: E402,F401

from services.rag_service.client import RAGServiceClientError
from v2.adapters.python_services.ktp_services import (
    KTP_DEFAULT_CROP_TYPE,
    KTP_DEFAULT_REGION,
    KTP_DEFAULT_TASK_TYPE,
)
from v2.shared.schemas import ObservationV2, PackArtifactView

if TYPE_CHECKING:
    from shared.schemas.service_results import (
        ConfidenceServiceResult,
        InferenceServiceResult,
        ModelRegistryResult,
        ReportServiceResult,
        TrainingTriggerResult,
        VisualizationServiceResult,
    )
    from v2.adapters.python_services.ktp_rag import KtpKnowledgeAdapter
    from v2.adapters.python_services.ktp_services import KtpExecutionContext, KtpServiceBundle


_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
_MAX_FILE_BYTES = 128 * 1024
_DEFAULT_SEARCH_LIMIT = 8


def run_demo_pack_answer(*, query: str) -> tuple[ObservationV2, list[PackArtifactView]]:
    return (
        ObservationV2(
            source="demo.pack_answer",
            status="success",
            summary="演示包成功回答了请求。",
            payload={"echo": query, "pack": "demo"},
        ),
        [
            PackArtifactView(
                pack_name="demo",
                artifact_type="text_card",
                title="演示包产物",
                content=f"演示包处理了: {query}",
            )
        ],
    )


def run_demo_fail(*, query: str) -> tuple[ObservationV2, list[PackArtifactView]]:
    return (
        ObservationV2(
            source="demo.fail",
            status="error",
            summary="演示失败工具故意返回了错误。",
            payload={"echo": query},
        ),
        [],
    )


def run_workspace_search(
    *,
    query: str,
    path: str | None = None,
    limit: int = _DEFAULT_SEARCH_LIMIT,
) -> tuple[ObservationV2, list[PackArtifactView]]:
    workspace_root = _resolve_workspace_path(path or ".")
    if workspace_root is None or not workspace_root.exists():
        return (
            ObservationV2(
                source="workspace.search",
                status="error",
                summary="工作区搜索失败：请求的路径不存在。",
                payload={"query": query, "path": path},
            ),
            [],
        )


    matches: list[str] = []
    normalized_query = query.strip().lower()
    for candidate in workspace_root.rglob("*"):
        if len(matches) >= max(1, limit):
            break
        if not candidate.is_file():
            continue
        if candidate.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".tif", ".tiff", ".pyc"}:
            continue
        try:
            if candidate.stat().st_size > _MAX_FILE_BYTES:
                continue
            content = candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(content.splitlines(), start=1):
            if normalized_query in line.lower():
                relative_path = candidate.relative_to(_WORKSPACE_ROOT)
                matches.append(f"{relative_path}:{line_number}: {line.strip()}")
                break

    summary = f"工作区搜索找到 {len(matches)} 条匹配结果（查询: {query!r}）。"
    return (
        ObservationV2(
            source="workspace.search",
            status="success",
            summary=summary,
            payload={"query": query, "matches": matches, "path": str(workspace_root)},
        ),
        [
            PackArtifactView(
                pack_name="workspace",
                artifact_type="search_results",
                title="工作区搜索",
                content="\n".join(matches) if matches else "未找到匹配的文件。",
            )
        ],
    )


def run_workspace_read_file(
    *,
    path: str,
) -> tuple[ObservationV2, list[PackArtifactView]]:
    resolved_path = _resolve_workspace_path(path)
    if resolved_path is None or not resolved_path.is_file():
        return (
            ObservationV2(
                source="workspace.read_file",
                status="error",
                summary="工作区读取失败：请求的文件不存在。",
                payload={"path": path},
            ),
            [],
        )

    try:
        if resolved_path.stat().st_size > _MAX_FILE_BYTES:
            return (
                ObservationV2(
                    source="workspace.read_file",
                    status="error",
                    summary="工作区读取拒绝：文件过大，无法内联显示。",
                    payload={"path": path},
                ),
                [],
            )
        content = resolved_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return (
            ObservationV2(
                source="workspace.read_file",
                status="error",
                summary=f"工作区读取失败: {exc}",
                payload={"path": path},
            ),
            [],
        )

    return (
        ObservationV2(
            source="workspace.read_file",
            status="success",
            summary=f"工作区文件加载成功。",
            payload={"path": str(resolved_path), "content": content},
        ),
        [
            PackArtifactView(
                pack_name="workspace",
                artifact_type="file_content",
                title=str(resolved_path.relative_to(_WORKSPACE_ROOT)),
                content=content,
            )
        ],
    )


def run_requires_confirmation(
    *,
    tool_name: str,
    **tool_input: object,
) -> tuple[ObservationV2, list[PackArtifactView]]:
    return (
        ObservationV2(
            source=tool_name,
            status="error",
            summary="approval_required",
            payload={"tool_name": tool_name, "tool_input": tool_input},
        ),
        [],
    )


def build_ktp_retrieve_knowledge_handler(
    *,
    adapter: KtpKnowledgeAdapter,
):
    def _handler(
        *,
        query: str,
        top_k: int = 3,
        region: str | None = None,
        crop_type: str | None = None,
        task_type: str | None = None,
        request_id: str | None = None,
        use_mock_backend: bool = False,
        image_path: str | None = None,
        extra_params: dict[str, object] | None = None,
    ) -> tuple[ObservationV2, list[PackArtifactView]]:
        del image_path, extra_params
        try:
            if use_mock_backend:
                from services.mock_services import MockRagService

                result = MockRagService().run_rag(
                    request_id=request_id,
                    user_query=query,
                    task_type=task_type,
                    region=region,
                    crop_type=crop_type,
                    top_k=top_k,
                )
            else:
                result = adapter.retrieve_knowledge(query=query, top_k=top_k)
        except RAGServiceClientError as exc:
            return (
                ObservationV2(
                    source="ktp.retrieve_knowledge",
                    status="error",
                    summary=f"KTP 知识检索失败: {exc}",
                    payload={"query": query},
                ),
                [],
            )

        sources_count = len(result.sources)
        chunks_count = len(result.results)
        summary = (
            f"KTP 知识检索完成，获取 {chunks_count} 个片段，{sources_count} 个来源。"
        )
        artifact_content = result.summary or "未检索到相关知识片段。"
        return (
            ObservationV2(
                source="ktp.retrieve_knowledge",
                status="success",
                summary=summary,
                payload={
                    "query": result.query,
                    "summary": result.summary,
                    "sources": result.sources,
                    "request_id": request_id,
                    "region": region,
                    "crop_type": crop_type,
                    "task_type": task_type,
                    "top_k": result.top_k,
                    "result_count": chunks_count,
                },
            ),
            [
                PackArtifactView(
                    pack_name="ktp",
                    artifact_type="knowledge_card",
                    title="KTP 知识检索",
                    content=artifact_content,
                )
            ],
        )

    return _handler


def build_ktp_lookup_model_registry_handler(
    *,
    bundle: KtpServiceBundle,
):
    def _handler(
        *,
        query: str,
        region: str = KTP_DEFAULT_REGION,
        crop_type: str = KTP_DEFAULT_CROP_TYPE,
        task_type: str = KTP_DEFAULT_TASK_TYPE,
        request_id: str | None = None,
        use_mock_backend: bool = False,
        image_path: str | None = None,
        extra_params: dict[str, object] | None = None,
    ) -> tuple[ObservationV2, list[PackArtifactView]]:
        del image_path, extra_params
        context = bundle.create_context(
            query=query,
            region=region,
            crop_type=crop_type,
            task_type=task_type,
            request_id=request_id,
            use_mock_backend=use_mock_backend,
        )
        result = bundle.ensure_model_lookup(context)
        summary = (
            f"KTP 模型注册查询完成，model_exists={result.model_exists} "
            f"区域={context.region}/{context.crop_type}/{context.task_type}。"
        )
        return (
            ObservationV2(
                source="ktp.lookup_model_registry",
                status="success",
                summary=summary,
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

    return _handler


def build_ktp_run_inference_workflow_handler(
    *,
    bundle: KtpServiceBundle,
):
    def _handler(
        *,
        query: str,
        region: str = KTP_DEFAULT_REGION,
        crop_type: str = KTP_DEFAULT_CROP_TYPE,
        task_type: str = KTP_DEFAULT_TASK_TYPE,
        request_id: str | None = None,
        use_mock_backend: bool = False,
        image_path: str | None = None,
        extra_params: dict[str, object] | None = None,
    ) -> tuple[ObservationV2, list[PackArtifactView]]:
        context = bundle.create_context(
            query=query,
            region=region,
            crop_type=crop_type,
            task_type=task_type,
            request_id=request_id,
            use_mock_backend=use_mock_backend,
            image_path=image_path,
            extra_params=extra_params,
        )
        result = bundle.ensure_inference(context)
        area_label = "LAI" if task_type == "lai_inversion" else "受影响面积"
        summary = (
            f"KTP 推理工作流完成，置信度={result.confidence:.2f}，"
            f"{area_label}={result.affected_area:.2f}。"
        )
        return (
            ObservationV2(
                source="ktp.run_inference_workflow",
                status="success",
                summary=summary,
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

    return _handler


def build_ktp_trigger_training_handler(
    *,
    bundle: KtpServiceBundle,
):
    def _handler(
        *,
        query: str,
        region: str = KTP_DEFAULT_REGION,
        crop_type: str = KTP_DEFAULT_CROP_TYPE,
        task_type: str = KTP_DEFAULT_TASK_TYPE,
        request_id: str | None = None,
        use_mock_backend: bool = False,
        image_path: str | None = None,
        extra_params: dict[str, object] | None = None,
    ) -> tuple[ObservationV2, list[PackArtifactView]]:
        del image_path
        context = bundle.create_context(
            query=query,
            region=region,
            crop_type=crop_type,
            task_type=task_type,
            request_id=request_id,
            use_mock_backend=use_mock_backend,
            extra_params=extra_params,
        )
        result = bundle.ensure_training(context)
        summary = (
            f"KTP 训练触发完成，job_id={result.training_job_id} "
            f"backend={context.training_backend or result.backend or 'unknown'}。"
        )
        return (
            ObservationV2(
                source="ktp.trigger_training",
                status="success",
                summary=summary,
                payload=_context_payload(context),
            ),
            [
                _artifact_from_training(
                    result=result,
                    backend=context.training_backend or "unknown",
                )
            ],
        )

    return _handler


def build_ktp_evaluate_confidence_handler(
    *,
    bundle: KtpServiceBundle,
):
    def _handler(
        *,
        query: str,
        region: str = KTP_DEFAULT_REGION,
        crop_type: str = KTP_DEFAULT_CROP_TYPE,
        task_type: str = KTP_DEFAULT_TASK_TYPE,
        request_id: str | None = None,
        use_mock_backend: bool = False,
        image_path: str | None = None,
        top_k: int = 3,
        extra_params: dict[str, object] | None = None,
    ) -> tuple[ObservationV2, list[PackArtifactView]]:
        context = bundle.create_context(
            query=query,
            region=region,
            crop_type=crop_type,
            task_type=task_type,
            request_id=request_id,
            use_mock_backend=use_mock_backend,
            image_path=image_path,
            top_k=top_k,
            extra_params=extra_params,
        )
        result = bundle.ensure_confidence(context)
        summary = (
            f"KTP 置信度评估完成，final_confidence={result.final_confidence:.2f} "
            f"label={result.final_label or 'unknown'}。"
        )
        return (
            ObservationV2(
                source="ktp.evaluate_confidence",
                status="success",
                summary=summary,
                payload=_context_payload(context),
            ),
            [
                _artifact_from_confidence(
                    result=result,
                    backend=context.confidence_backend or "unknown",
                )
            ],
        )

    return _handler


def build_ktp_build_report_handler(
    *,
    bundle: KtpServiceBundle,
):
    def _handler(
        *,
        query: str,
        region: str = KTP_DEFAULT_REGION,
        crop_type: str = KTP_DEFAULT_CROP_TYPE,
        task_type: str = KTP_DEFAULT_TASK_TYPE,
        request_id: str | None = None,
        use_mock_backend: bool = False,
        image_path: str | None = None,
        top_k: int = 3,
        extra_params: dict[str, object] | None = None,
    ) -> tuple[ObservationV2, list[PackArtifactView]]:
        context = bundle.create_context(
            query=query,
            region=region,
            crop_type=crop_type,
            task_type=task_type,
            request_id=request_id,
            use_mock_backend=use_mock_backend,
            image_path=image_path,
            top_k=top_k,
            extra_params=extra_params,
        )
        result = bundle.ensure_report(context)
        summary = (
            f"KTP 报告生成完成，共 {len(result.sections)} 个章节 "
            f"backend={context.report_backend or 'unknown'}。"
        )
        return (
            ObservationV2(
                source="ktp.build_report",
                status="success",
                summary=summary,
                payload=_context_payload(context),
            ),
            [
                _artifact_from_report(
                    result=result,
                    backend=context.report_backend or "unknown",
                )
            ],
        )

    return _handler


def build_ktp_build_visualization_handler(
    *,
    bundle: KtpServiceBundle,
):
    def _handler(
        *,
        query: str,
        region: str = KTP_DEFAULT_REGION,
        crop_type: str = KTP_DEFAULT_CROP_TYPE,
        task_type: str = KTP_DEFAULT_TASK_TYPE,
        request_id: str | None = None,
        use_mock_backend: bool = False,
        image_path: str | None = None,
        top_k: int = 3,
        extra_params: dict[str, object] | None = None,
    ) -> tuple[ObservationV2, list[PackArtifactView]]:
        context = bundle.create_context(
            query=query,
            region=region,
            crop_type=crop_type,
            task_type=task_type,
            request_id=request_id,
            use_mock_backend=use_mock_backend,
            image_path=image_path,
            top_k=top_k,
            extra_params=extra_params,
        )
        result = bundle.ensure_visualization(context)
        summary = (
            f"KTP 可视化生成完成，共 {len(result.sections)} 个仪表盘章节 "
            f"backend={context.visualization_backend or 'unknown'}。"
        )
        return (
            ObservationV2(
                source="ktp.build_visualization",
                status="success",
                summary=summary,
                payload=_context_payload(context),
            ),
            [
                _artifact_from_visualization(
                    result=result,
                    backend=context.visualization_backend or "unknown",
                )
            ],
        )

    return _handler


def _context_payload(context: KtpExecutionContext) -> dict[str, Any]:
    return {
        "request_id": context.request_id,
        "query": context.query,
        "region": context.region,
        "crop_type": context.crop_type,
        "task_type": context.task_type,
        "use_mock_backend": context.use_mock_backend,
        "top_k": context.top_k,
        "backend_notes": list(context.backend_notes),
        "backends": {
            "model_lookup": context.model_lookup_backend,
            "inference": context.inference_backend,
            "rag": context.rag_backend,
            "training": context.training_backend,
            "report": context.report_backend,
            "confidence": context.confidence_backend,
            "visualization": context.visualization_backend,
        },
        "model_registry_result": _dump(context.model_registry_result),
        "inference_result": _dump(context.inference_result),
        "knowledge_result": _dump(context.rag_result),
        "rag_result": _dump(context.rag_result),
        "training_result": _dump(context.training_result),
        "report_result": _dump(context.report_result),
        "confidence_result": _dump(context.confidence_result),
        "visualization_result": _dump(context.visualization_result),
    }


def _artifact_from_model_lookup(
    *,
    result: ModelRegistryResult,
    backend: str,
    context: KtpExecutionContext,
) -> PackArtifactView:
    content = (
        f"区域={context.region}\n"
        f"对象类型={context.crop_type}\n"
        f"任务类型={context.task_type}\n"
        f"模型存在={result.model_exists}\n"
        f"模型名称={result.model_name or '无'}\n"
        f"模型版本={result.model_version or '无'}\n"
        f"后端={backend}"
    )
    return PackArtifactView(
        pack_name="ktp",
        artifact_type="registry_card",
        title="KTP 模型注册查询",
        content=content,
        uri=result.artifact_uri,
    )


def _artifact_from_inference(
    *,
    result: InferenceServiceResult,
    backend: str,
    task_type: str | None = None,
) -> PackArtifactView:
    area_label = "LAI 值" if task_type == "lai_inversion" else "受影响面积"
    return PackArtifactView(
        pack_name="ktp",
        artifact_type="inference_card",
        title="KTP 推理工作流",
        content=(
            f"后端={backend}\n"
            f"模型={result.model_name or '未知'}@{result.model_version}\n"
            f"置信度={result.confidence:.4f}\n"
            f"{area_label}={result.affected_area:.2f}"
        ),
        uri=result.mask_uri,
    )


def _artifact_from_training(
    *,
    result: TrainingTriggerResult,
    backend: str,
) -> PackArtifactView:
    return PackArtifactView(
        pack_name="ktp",
        artifact_type="training_card",
        title="KTP 训练触发",
        content=(
            f"后端={backend}\n"
            f"训练已触发={result.training_triggered}\n"
            f"训练任务ID={result.training_job_id}"
        ),
    )


def _artifact_from_confidence(
    *,
    result: ConfidenceServiceResult,
    backend: str,
) -> PackArtifactView:
    return PackArtifactView(
        pack_name="ktp",
        artifact_type="confidence_card",
        title="KTP 置信度评估",
        content=(
            f"后端={backend}\n"
            f"最终置信度={result.final_confidence:.4f}\n"
            f"最终等级={result.final_label or '未知'}\n"
            f"说明={result.explanation}"
        ),
    )


def _artifact_from_report(
    *,
    result: ReportServiceResult,
    backend: str,
) -> PackArtifactView:
    return PackArtifactView(
        pack_name="ktp",
        artifact_type="report_card",
        title=result.title,
        content=(
            f"后端={backend}\n"
            f"章节={', '.join(result.sections)}\n"
            f"报告ID={result.report_id or '无'}"
        ),
        uri=result.report_uri,
    )


def _artifact_from_visualization(
    *,
    result: VisualizationServiceResult,
    backend: str,
) -> PackArtifactView:
    return PackArtifactView(
        pack_name="ktp",
        artifact_type="visualization_card",
        title=result.title,
        content=(
            f"后端={backend}\n"
            f"可视化ID={result.visualization_id or '无'}\n"
            f"章节={', '.join(result.sections)}"
        ),
        uri=result.visualization_uri,
    )


def _dump(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    return value.model_dump(mode="json")


def _resolve_workspace_path(raw_path: str) -> Path | None:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = (_WORKSPACE_ROOT / candidate).resolve()
    else:
        candidate = candidate.resolve()

    try:
        candidate.relative_to(_WORKSPACE_ROOT)
    except ValueError:
        return None
    return candidate


_PROSAIL_ENGINE = None

def _get_prosail_engine():
    global _PROSAIL_ENGINE
    if _PROSAIL_ENGINE is None:
        from prosail_api import PROSAILEngine
        _PROSAIL_ENGINE = PROSAILEngine()
    return _PROSAIL_ENGINE


def run_prosail_simulation(
    *,
    N: float = 1.5,
    Cab: float = 40.0,
    Car: float = 8.0,
    Ant: float = 0.0,
    Cbrown: float = 0.0,
    Cw: float = 0.01,
    Cm: float = 0.01,
    LIDFa: float = 0.0,
    LIDFb: float = 0.0,
    TypeLidf: int = 1,
    lai: float = 2.0,
    q: float = 0.1,
    tts: float = 30.0,
    tto: float = 0.0,
    psi: float = 0.0,
    rsoil: float = 0.1,
    query: str | None = None,
) -> tuple[ObservationV2, list[PackArtifactView]]:
    try:
        from prosail import prosail

        rdot, rsot, rddt, rsdt = prosail(
            N, Cab, Car, Ant, Cbrown, Cw, Cm,
            LIDFa, LIDFb, TypeLidf, lai, q, tts, tto, psi, rsoil
        )

        wavelengths = [f"{400 + i * 10}nm" for i in range(len(rdot))]
        result_text = (
            f"PROSAIL 光谱模拟完成。\n"
            f"参数: N={N}, Cab={Cab}, Car={Car}, Cw={Cw}, Cm={Cm}, LAI={lai}\n"
            f"几何: tts={tts}, tto={tto}, psi={psi}\n"
            f"光谱范围: 400-2500nm (210 个点)\n"
            f"rdot (方向-半球反射): {len(rdot)} 个值\n"
            f"rsot (半球-方向反射): {len(rsot)} 个值\n"
        )

        return (
            ObservationV2(
                source="prosail.simulation",
                status="success",
                summary="PROSAIL 光谱模拟完成。",
                payload={
                    "N": N, "Cab": Cab, "Car": Car, "Cw": Cw, "Cm": Cm, "LAI": lai,
                    "geometry": {"tts": tts, "tto": tto, "psi": psi},
                    "wavelength_count": len(rdot),
                },
            ),
            [
                PackArtifactView(
                    pack_name="prosail",
                    artifact_type="simulation_result",
                    title="PROSAIL 光谱模拟",
                    content=result_text,
                )
            ],
        )
    except Exception as exc:
        return (
            ObservationV2(
                source="prosail.simulation",
                status="error",
                summary=f"PROSAIL 模拟失败: {exc}",
                payload={"error": str(exc)},
            ),
            [],
        )


def run_prosail_build_lut(
    *,
    params: dict | None = None,
    output_path: str = "var/runtime/prosail_lut.pkl",
    query: str | None = None,
) -> tuple[ObservationV2, list[PackArtifactView]]:
    try:
        engine = _get_prosail_engine()
        if params is None:
            from prosail_api import create_default_params
            params = create_default_params()

        lut_id = engine.build_lut(params)
        engine.save_lut(output_path)

        return (
            ObservationV2(
                source="prosail.build_lut",
                status="success",
                summary=f"PROSAIL 查找表构建完成，ID: {lut_id}",
                payload={"lut_id": lut_id, "output_path": output_path, "params": params},
            ),
            [
                PackArtifactView(
                    pack_name="prosail",
                    artifact_type="lut_card",
                    title="PROSAIL 构建查找表",
                    content=f"查找表ID: {lut_id}\n输出路径: {output_path}\n条目数: {len(engine.lut) if engine.lut is not None else 0}",
                )
            ],
        )
    except Exception as exc:
        return (
            ObservationV2(
                source="prosail.build_lut",
                status="error",
                summary=f"PROSAIL 查找表构建失败: {exc}",
                payload={"error": str(exc)},
            ),
            [],
        )


def run_prosail_load_lut(
    *,
    lut_path: str,
    query: str | None = None,
) -> tuple[ObservationV2, list[PackArtifactView]]:
    try:
        engine = _get_prosail_engine()
        engine.load_lut(lut_path)

        return (
            ObservationV2(
                source="prosail.load_lut",
                status="success",
                summary=f"PROSAIL 查找表已加载: {engine.lut_id}",
                payload={"lut_id": engine.lut_id, "lut_path": lut_path, "lut_size": len(engine.lut)},
            ),
            [
                PackArtifactView(
                    pack_name="prosail",
                    artifact_type="lut_card",
                    title="PROSAIL 加载查找表",
                    content=f"查找表ID: {engine.lut_id}\n路径: {lut_path}\n条目数: {len(engine.lut)}",
                )
            ],
        )
    except Exception as exc:
        return (
            ObservationV2(
                source="prosail.load_lut",
                status="error",
                summary=f"PROSAIL 查找表加载失败: {exc}",
                payload={"error": str(exc)},
            ),
            [],
        )


def run_prosail_invert_lai(
    *,
    reflectance: dict | None = None,
    image_path: str | None = None,
    crop_type: str | None = None,
    region: str | None = None,
    task_type: str | None = None,
    lut_path: str | None = None,
    method: str = "min_distance",
    options: dict | None = None,
    query: str | None = None,
    **_unused: object,
) -> tuple[ObservationV2, list[PackArtifactView]]:
    try:
        if image_path:
            return run_prosail_invert_lai_tif(
                image_path=image_path,
                lut_path=lut_path,
                ndvi_threshold=float((options or {}).get("ndvi_threshold", 0.2)),
                scale_factor=float((options or {}).get("scale_factor", 10000.0)),
                method=method,
                output_dir=(options or {}).get("output_dir"),
                query=query,
            )

        engine = _get_prosail_engine()

        if reflectance is None:
            return (
                ObservationV2(
                    source="prosail.invert_lai",
                    status="error",
                    summary="请提供 reflectance 反射率字典，或者提供 image_path 走 TIF 反演流程。",
                    payload={"error": "missing_reflectance"},
                ),
                [],
            )

        if engine.lut is None and lut_path:
            engine.load_lut(lut_path)
        elif engine.lut is None:
            default_lut = str(_WORKSPACE_ROOT / "prosail_python" / "demo_lut.pkl")
            if Path(default_lut).exists():
                engine.load_lut(default_lut)
            else:
                return (
                    ObservationV2(
                        source="prosail.invert_lai",
                        status="error",
                        summary="未加载查找表，请提供 lut_path 或先构建查找表。",
                        payload={"error": "未加载查找表"},
                    ),
                    [],
                )

        if options is None:
            options = {}

        if method == "default":
            method = "min_distance"

        lut_n_bands = engine.lut.shape[1] - 6
        s2_band_wavelengths = {
            "B1": 443, "B2": 490, "B3": 560, "B4": 665, "B5": 705,
            "B6": 740, "B7": 783, "B8": 842, "B8A": 865, "B9": 945,
        }
        lut_wavelengths = [490, 560, 665, 842]
        required_bands = ["B2", "B3", "B4", "B8"]

        input_bands = [k for k in reflectance.keys() if k.lower().startswith("b") and k[1:].isdigit()]
        if input_bands:
            available_bands = []
            for lut_wl in lut_wavelengths:
                closest_band = None
                min_diff = float("inf")
                for band in input_bands:
                    wl = s2_band_wavelengths.get(band)
                    if wl:
                        diff = abs(wl - lut_wl)
                        if diff < min_diff:
                            min_diff = diff
                            closest_band = band
                if closest_band:
                    available_bands.append(closest_band)

            missing_bands = [b for b in required_bands if b not in input_bands]
            if missing_bands:
                return (
                    ObservationV2(
                        source="prosail.invert_lai",
                        status="error",
                        summary=f"LAI 反演需要 Sentinel-2 波段 {required_bands}，但缺少: {missing_bands}。请提供 B8 (近红外) 反射率数据。",
                        payload={"error": f"缺少必需波段: {missing_bands}", "required_bands": required_bands},
                    ),
                    [],
                )

            if len(available_bands) >= lut_n_bands:
                options["bands"] = available_bands[:lut_n_bands]

        result = engine.invert_lai(reflectance, method=method, options=options)

        return (
            ObservationV2(
                source="prosail.invert_lai",
                status="success",
                summary=f"LAI 反演完成: LAI={result['LAI']:.2f}, confidence={result['confidence']:.4f}",
                payload={
                    "LAI": result["LAI"],
                    "confidence": result["confidence"],
                    "parameters": result["parameters"],
                    "distance": result["distance"],
                },
            ),
            [
                PackArtifactView(
                    pack_name="prosail",
                    artifact_type="inversion_result",
                    title="LAI 反演结果",
                    content=(
                        f"LAI: {result['LAI']:.4f}\n"
                        f"置信度: {result['confidence']:.4f}\n"
                        f"距离: {result['distance']:.6f}\n"
                        f"参数:\n"
                        f"  Cab: {result['parameters']['Cab']:.2f}\n"
                        f"  Car: {result['parameters']['Car']:.2f}\n"
                        f"  Cw: {result['parameters']['Cw']:.6f}\n"
                        f"  Cm: {result['parameters']['Cm']:.6f}\n"
                        f"  N: {result['parameters']['N']:.4f}\n"
                        f"输入反射率: {reflectance}"
                    ),
                )
            ],
        )
    except Exception as exc:
        return (
            ObservationV2(
                source="prosail.invert_lai",
                status="error",
                summary=f"LAI 反演失败: {exc}",
                payload={"error": str(exc)},
            ),
            [],
        )


def _build_default_lut_params() -> dict:
    return {
        "parameters": {
            "LAI": {"min": 0, "max": 6, "step": 0.5},
            "Cab": {"min": 20, "max": 80, "step": 10},
            "Car": {"min": 5, "max": 15, "step": 5},
            "Cw": {"min": 0.005, "max": 0.03, "step": 0.005},
            "Cm": {"min": 0.005, "max": 0.015, "step": 0.005},
            "N": {"min": 1.2, "max": 1.8, "step": 0.2},
        },
        "geometry": {
            "LIDFa": 30, "LIDFb": 0, "TypeLidf": 2,
            "solar_zenith": 30, "view_zenith": 10,
            "azimuth": 90, "hotspot": 0.01,
        },
        "soil": {"type": "dry"},
        "bands": [490, 560, 665, 842],
    }


def run_prosail_invert_lai_tif(
    *,
    image_path: str,
    lut_path: str | None = None,
    ndvi_threshold: float = 0.2,
    scale_factor: float = 10000.0,
    method: str = "min_distance",
    output_dir: str | None = None,
    query: str | None = None,
) -> tuple[ObservationV2, list[PackArtifactView]]:
    try:
        import rasterio
        import numpy as np

        img_path = Path(image_path).expanduser().resolve()
        if not img_path.exists():
            return (
                ObservationV2(
                    source="prosail.invert_lai_tif",
                    status="error",
                    summary=f"输入 TIF 文件不存在: {image_path}",
                    payload={"error": "file_not_found", "path": str(img_path)},
                ),
                [],
            )

        engine = _get_prosail_engine()

        if engine.lut is None and lut_path:
            engine.load_lut(str(Path(lut_path).expanduser().resolve()))
        elif engine.lut is None:
            default_lut = str(_WORKSPACE_ROOT / "prosail_python" / "demo_lut.pkl")
            if Path(default_lut).exists():
                engine.load_lut(default_lut)
            else:
                params = _build_default_lut_params()
                engine.build_lut(params)
                engine.save_lut(default_lut)

        with rasterio.open(str(img_path)) as src:
            img = src.read()
            profile = src.profile
            n_bands = img.shape[0]
            height, width = img.shape[1], img.shape[2]

        img_float = img.astype(np.float32) / scale_factor
        img_float = np.clip(img_float, 0, 1)

        s2_band_map = {
            1: "B2", 2: "B3", 3: "B4", 4: "B8",
            5: "B5", 6: "B6", 7: "B7", 8: "B8A", 9: "B9", 10: "B11", 11: "B12",
        }
        required_bands = ["B2", "B3", "B4", "B8"]
        band_indices = {}
        for i in range(min(n_bands, 12)):
            band_name = s2_band_map.get(i + 1)
            if band_name in required_bands:
                band_indices[band_name] = i

        missing = [b for b in required_bands if b not in band_indices]
        if missing:
            if n_bands >= 4:
                band_indices = {"B2": 0, "B3": 1, "B4": 2, "B8": min(3, n_bands - 1)}
            else:
                return (
                    ObservationV2(
                        source="prosail.invert_lai_tif",
                        status="error",
                        summary=f"TIF 至少需要 4 个波段 (B2/B3/B4/B8)，当前 {n_bands} 个。缺少: {missing}",
                        payload={"error": "insufficient_bands", "n_bands": n_bands, "missing": missing},
                    ),
                    [],
                )

        b2 = img_float[band_indices["B2"]]
        b3 = img_float[band_indices["B3"]]
        b4 = img_float[band_indices["B4"]]
        b8 = img_float[band_indices["B8"]]

        ndvi = (b8 - b4) / (b8 + b4 + 1e-10)
        vegetation_mask = ndvi > ndvi_threshold

        lai_map = np.full((height, width), np.nan, dtype=np.float32)
        confidence_map = np.full((height, width), np.nan, dtype=np.float32)

        lut_spectrum = engine.lut[:, 6:10]
        lut_lai = engine.lut[:, 0]

        veg_pixels = np.where(vegetation_mask)
        n_veg = len(veg_pixels[0])

        if n_veg > 0:
            obs_spectra = np.stack([
                b2[veg_pixels],
                b3[veg_pixels],
                b4[veg_pixels],
                b8[veg_pixels],
            ], axis=1)

            chunk_size = 5000
            for start in range(0, n_veg, chunk_size):
                end = min(start + chunk_size, n_veg)
                chunk = obs_spectra[start:end]
                distances = np.sqrt(np.sum((lut_spectrum[None, :, :] - chunk[:, None, :]) ** 2, axis=2))
                min_indices = np.argmin(distances, axis=1)

                for j in range(end - start):
                    global_j = start + j
                    r, c = veg_pixels[0][global_j], veg_pixels[1][global_j]
                    lai_map[r, c] = lut_lai[min_indices[j]]
                    confidence_map[r, c] = 1.0 / (1.0 + distances[j, min_indices[j]])

        if output_dir:
            out_dir = Path(output_dir).expanduser().resolve()
        else:
            out_dir = img_path.parent
        out_dir.mkdir(parents=True, exist_ok=True)

        stem = img_path.stem
        lai_path = out_dir / f"{stem}_lai.tif"
        conf_path = out_dir / f"{stem}_lai_confidence.tif"

        output_profile = profile.copy()
        output_profile.update({
            "dtype": "float32",
            "count": 1,
            "nodata": float(np.nan),
        })

        with rasterio.open(str(lai_path), "w", **output_profile) as dst:
            dst.write(lai_map, 1)

        with rasterio.open(str(conf_path), "w", **output_profile) as dst:
            dst.write(confidence_map, 1)

        valid_lai = lai_map[~np.isnan(lai_map)]
        stats = {}
        if len(valid_lai) > 0:
            stats = {
                "lai_min": float(np.min(valid_lai)),
                "lai_max": float(np.max(valid_lai)),
                "lai_mean": float(np.mean(valid_lai)),
                "lai_std": float(np.std(valid_lai)),
                "n_vegetation_pixels": int(n_veg),
                "vegetation_ratio": float(n_veg / (height * width)),
                "ndvi_threshold": float(ndvi_threshold),
            }

        artifacts = [
            PackArtifactView(
                pack_name="prosail",
                artifact_type="lai_geotiff",
                title=f"LAI反演结果 ({stem})",
                content=(
                    f"LAI统计: mean={stats.get('lai_mean', 0):.2f}, "
                    f"min={stats.get('lai_min', 0):.2f}, max={stats.get('lai_max', 0):.2f}\n"
                    f"植被像元: {stats.get('n_vegetation_pixels', 0)} ({stats.get('vegetation_ratio', 0)*100:.1f}%)\n"
                    f"NDVI阈值: {ndvi_threshold}\n"
                    f"反演方法: {method}"
                ),
                uri=f"file://{lai_path}",
            ),
            PackArtifactView(
                pack_name="prosail",
                artifact_type="lai_confidence_geotiff",
                title=f"LAI置信度 ({stem})",
                content=f"LAI反演置信度空间分布",
                uri=f"file://{conf_path}",
            ),
        ]

        return (
            ObservationV2(
                source="prosail.invert_lai_tif",
                status="success",
                summary=(
                    f"LAI反演完成: 输入 {stem}.tif ({n_bands}波段, {height}x{width}), "
                    f"植被像元 {n_veg} ({100*n_veg/(height*width):.1f}%), "
                    f"LAI均值={stats.get('lai_mean', 0):.2f}"
                ),
                payload={
                    "input_path": str(img_path),
                    "lai_output": str(lai_path),
                    "confidence_output": str(conf_path),
                    **stats,
                },
            ),
            artifacts,
        )
    except Exception as exc:
        logger.exception("prosail.invert_lai_tif failed: %s", exc)
        return (
            ObservationV2(
                source="prosail.invert_lai_tif",
                status="error",
                summary=f"LAI TIF反演失败: {exc}",
                payload={"error": str(exc)},
            ),
            [],
        )
