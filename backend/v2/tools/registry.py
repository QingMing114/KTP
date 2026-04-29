from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from v2.adapters.python_services.ktp_services import (
    KtpServiceBundle,
    build_default_ktp_service_bundle,
)
from v2.adapters.python_services.ktp_rag import (
    KtpKnowledgeAdapter,
    build_default_ktp_knowledge_adapter,
)
from v2.shared.schemas import ObservationV2, PackArtifactView, ToolSpecV2
from v2.tools.apsim_adapter import run_apsim_crop_simulation
from v2.tools.handlers import (
    build_ktp_build_report_handler,
    build_ktp_build_visualization_handler,
    build_ktp_evaluate_confidence_handler,
    build_ktp_lookup_model_registry_handler,
    build_ktp_retrieve_knowledge_handler,
    build_ktp_run_inference_workflow_handler,
    build_ktp_trigger_training_handler,
    run_demo_fail,
    run_demo_pack_answer,
    run_prosail_build_lut,
    run_prosail_invert_lai,
    run_prosail_invert_lai_tif,
    run_prosail_load_lut,
    run_prosail_simulation,
    run_requires_confirmation,
    run_workspace_read_file,
    run_workspace_search,
)


ToolHandler = Callable[..., tuple[ObservationV2, list[PackArtifactView]]]


class ToolNotFoundError(Exception):
    pass


@dataclass
class ToolDefinition:
    spec: ToolSpecV2
    handler: ToolHandler


@dataclass
class ToolRegistryV2:
    definitions: dict[str, ToolDefinition]
    ktp_knowledge_adapter: KtpKnowledgeAdapter | None = None
    ktp_service_bundle: KtpServiceBundle | None = None

    def list_tools(self) -> list[ToolSpecV2]:
        return [definition.spec for definition in self.definitions.values()]

    def get_definition(self, tool_name: str) -> ToolDefinition:
        return self.definitions[tool_name]

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self.definitions

    def register(self, name: str, spec: ToolSpecV2, handler: ToolHandler) -> None:
        self.definitions[name] = ToolDefinition(spec=spec, handler=handler)

    def unregister(self, name: str) -> bool:
        if name in self.definitions:
            del self.definitions[name]
            return True
        return False

    def invoke(
        self,
        *,
        tool_name: str,
        tool_input: dict[str, object],
    ) -> tuple[ObservationV2, list[PackArtifactView]]:
        if not self.has_tool(tool_name):
            raise ToolNotFoundError(
                f"Tool '{tool_name}' not found in registry. "
                f"Available: {list(self.definitions.keys())}"
            )
        return self.get_definition(tool_name).handler(**tool_input)


def build_default_tool_registry(
    *,
    ktp_knowledge_adapter: KtpKnowledgeAdapter | None = None,
    ktp_service_bundle: KtpServiceBundle | None = None,
) -> ToolRegistryV2:
    resolved_ktp_knowledge_adapter = ktp_knowledge_adapter or build_default_ktp_knowledge_adapter()
    resolved_ktp_service_bundle = ktp_service_bundle or build_default_ktp_service_bundle()
    return ToolRegistryV2(
        ktp_knowledge_adapter=resolved_ktp_knowledge_adapter,
        ktp_service_bundle=resolved_ktp_service_bundle,
        definitions={
            "direct_answer": ToolDefinition(
                spec=ToolSpecV2(
                    name="direct_answer",
                    display_name="直接回答",
                    description="Return a direct language answer without external tool execution.",
                    visibility="public",
                    category="conversation",
                    usage_hint="Use when no external pack/tool is needed.",
                    input_schema={},
                    surface_visibility="internal",
                    enabled_by_default=False,
                    capabilities=["direct_response", "general_qa"],
                ),
                handler=lambda **_kwargs: (
                    ObservationV2(
                        source="direct_answer",
                        status="success",
                        summary="Direct answers are synthesized by the runtime, not by invoking this tool.",
                    ),
                    [],
                ),
            ),
            "demo.pack_answer": ToolDefinition(
                spec=ToolSpecV2(
                    name="demo.pack_answer",
                    display_name="演示回答",
                    description="Demo pack tool that returns a structured answer artifact.",
                    visibility="bounded",
                    category="debug",
                    pack_name="demo",
                    usage_hint="Use for proving the runtime can invoke a pack-backed tool.",
                    input_schema={"query": "string"},
                    capabilities=["tool_smoke_test", "artifact_emission"],
                    produces_artifacts=["text_card"],
                ),
                handler=run_demo_pack_answer,
            ),
            "demo.fail": ToolDefinition(
                spec=ToolSpecV2(
                    name="demo.fail",
                    display_name="演示失败工具",
                    description="Demo pack tool that intentionally fails so replan behavior can be exercised.",
                    visibility="bounded",
                    category="debug",
                    pack_name="demo",
                    usage_hint="Use only for testing bounded replan and safe fallback behavior.",
                    input_schema={"query": "string"},
                    surface_visibility="debug",
                    enabled_by_default=False,
                    capabilities=["failure_path", "replan_smoke_test"],
                ),
                handler=run_demo_fail,
            ),
            "workspace.search": ToolDefinition(
                spec=ToolSpecV2(
                    name="workspace.search",
                    display_name="工作区搜索",
                    description="Search the local workspace for code, docs, or config matches.",
                    visibility="public",
                    category="workspace",
                    usage_hint="Use before reading files when you only know a keyword or symbol.",
                    input_schema={"query": "string", "path": "string?", "limit": "integer?"},
                    safety_level="safe",
                    surface_visibility="web",
                    enabled_by_default=True,
                    capabilities=["workspace_search", "code_search"],
                    requires_context=["query"],
                    produces_artifacts=["search_results"],
                ),
                handler=run_workspace_search,
            ),
            "workspace.read_file": ToolDefinition(
                spec=ToolSpecV2(
                    name="workspace.read_file",
                    display_name="读取文件",
                    description="Read a workspace text file for grounded answers.",
                    visibility="public",
                    category="workspace",
                    usage_hint="Use after search when you need the actual file contents.",
                    input_schema={"path": "string"},
                    safety_level="safe",
                    surface_visibility="web",
                    enabled_by_default=True,
                    capabilities=["file_read", "grounded_lookup"],
                    requires_context=["path"],
                    produces_artifacts=["file_content"],
                ),
                handler=run_workspace_read_file,
            ),
            "workspace.write": ToolDefinition(
                spec=ToolSpecV2(
                    name="workspace.write",
                    display_name="写入文件",
                    description="Reserved mutating workspace tool that requires user approval before use.",
                    visibility="bounded",
                    category="workspace",
                    usage_hint="Not available in the current web surface.",
                    input_schema={"path": "string", "content": "string"},
                    safety_level="dangerous",
                    surface_visibility="web",
                    user_confirmation_required=True,
                    enabled_by_default=True,
                    capabilities=["file_write"],
                    requires_context=["path", "content"],
                ),
                handler=lambda **tool_input: run_requires_confirmation(
                    tool_name="workspace.write",
                    **tool_input,
                ),
            ),
            "shell.exec": ToolDefinition(
                spec=ToolSpecV2(
                    name="shell.exec",
                    display_name="执行 Shell 命令",
                    description="Reserved terminal execution tool that requires approval before use.",
                    visibility="bounded",
                    category="debug",
                    usage_hint="Not available in the current web surface.",
                    input_schema={"command": "string"},
                    safety_level="dangerous",
                    surface_visibility="debug",
                    user_confirmation_required=True,
                    enabled_by_default=False,
                    capabilities=["shell_execution"],
                    requires_context=["command"],
                ),
                handler=lambda **tool_input: run_requires_confirmation(
                    tool_name="shell.exec",
                    **tool_input,
                ),
            ),
            "knowledge.search_local": ToolDefinition(
                spec=ToolSpecV2(
                    name="knowledge.search_local",
                    display_name="搜索本地知识",
                    description="Retrieve grounded KTP knowledge snippets and source links from the local knowledge adapter.",
                    visibility="public",
                    category="knowledge",
                    usage_hint="Use when the answer should cite local domain knowledge or sources.",
                    input_schema={"query": "string", "top_k": "integer?"},
                    safety_level="safe",
                    surface_visibility="web",
                    enabled_by_default=True,
                    capabilities=["grounded_qa", "source_retrieval"],
                    requires_context=["query"],
                    produces_artifacts=["knowledge_card"],
                ),
                handler=build_ktp_retrieve_knowledge_handler(adapter=resolved_ktp_knowledge_adapter),
            ),
            "ktp.analysis_pipeline": ToolDefinition(
                spec=ToolSpecV2(
                    name="ktp.analysis_pipeline",
                    display_name="KTP 分析管线",
                    description="宏工具：运行完整的 KTP 分析工作流，返回报告、置信度和可视化产物。",
                    visibility="public",
                    category="analysis",
                    pack_name="ktp",
                    usage_hint="Use for real KTP task execution when the user asks for analysis, report, confidence, or visualization.",
                    input_schema={
                        "query": "string",
                        "region": "string?",
                        "crop_type": "string?",
                        "task_type": "string?",
                        "image_path": "string?",
                        "include_knowledge": "boolean?",
                        "include_visualization": "boolean?",
                    },
                    safety_level="caution",
                    surface_visibility="web",
                    enabled_by_default=True,
                    is_macro=True,
                    capabilities=["analysis_pipeline", "report_generation", "confidence_scoring"],
                    requires_context=["query"],
                    produces_artifacts=["registry_card", "inference_card", "report_card", "confidence_card", "visualization_card"],
                ),
                handler=lambda **_tool_input: (
                    ObservationV2(
                        source="ktp.analysis_pipeline",
                        status="success",
                        summary="ktp.analysis_pipeline is a macro tool executed by the runtime.",
                    ),
                    [],
                ),
            ),
            "ktp.explain_knowledge": ToolDefinition(
                spec=ToolSpecV2(
                    name="ktp.explain_knowledge",
                    display_name="KTP 知识解释",
                    description="Macro-friendly knowledge explanation tool that retrieves sources and supports explanatory answers.",
                    visibility="public",
                    category="knowledge",
                    pack_name="ktp",
                    usage_hint="Use for NDVI/EVI style explanation requests that should stay grounded in KTP knowledge.",
                    input_schema={"query": "string", "top_k": "integer?"},
                    safety_level="safe",
                    surface_visibility="web",
                    enabled_by_default=True,
                    capabilities=["knowledge_explanation", "source_retrieval"],
                    requires_context=["query"],
                    produces_artifacts=["knowledge_card"],
                ),
                handler=build_ktp_retrieve_knowledge_handler(adapter=resolved_ktp_knowledge_adapter),
            ),
            "ktp.retrieve_knowledge": ToolDefinition(
                spec=ToolSpecV2(
                    name="ktp.retrieve_knowledge",
                    display_name="知识检索",
                    description="Use the existing KTP RAG service to retrieve structured knowledge snippets.",
                    visibility="bounded",
                    category="knowledge",
                    pack_name="ktp",
                    usage_hint="Use for knowledge-grounded questions when a KTP pack tool is preferable to a direct answer.",
                    input_schema={"query": "string", "top_k": "integer?"},
                    safety_level="safe",
                    surface_visibility="web",
                    enabled_by_default=True,
                    capabilities=["grounded_qa", "source_retrieval"],
                    requires_context=["query"],
                    produces_artifacts=["knowledge_card"],
                ),
                handler=build_ktp_retrieve_knowledge_handler(adapter=resolved_ktp_knowledge_adapter),
            ),
            "ktp.lookup_model_registry": ToolDefinition(
                spec=ToolSpecV2(
                    name="ktp.lookup_model_registry",
                    display_name="模型注册查询",
                    description="Look up KTP model availability for a region/crop/task combination.",
                    visibility="bounded",
                    category="analysis",
                    pack_name="ktp",
                    usage_hint="Use when the runtime needs to inspect whether KTP already has a ready model.",
                    input_schema={"region": "string", "crop_type": "string", "task_type": "string"},
                    safety_level="caution",
                    surface_visibility="web",
                    enabled_by_default=True,
                    capabilities=["model_discovery", "readiness_check"],
                    requires_context=["region", "crop_type", "task_type"],
                    produces_artifacts=["registry_card"],
                ),
                handler=build_ktp_lookup_model_registry_handler(bundle=resolved_ktp_service_bundle),
            ),
            "ktp.run_inference_workflow": ToolDefinition(
                spec=ToolSpecV2(
                    name="ktp.run_inference_workflow",
                    display_name="推理工作流",
                    description="Run the KTP inference workflow and return mask-oriented artifacts.",
                    visibility="bounded",
                    category="analysis",
                    pack_name="ktp",
                    usage_hint="Use when the runtime should execute one bounded KTP inference step.",
                    input_schema={
                        "region": "string",
                        "crop_type": "string",
                        "task_type": "string",
                        "image_path": "string",
                    },
                    safety_level="caution",
                    surface_visibility="web",
                    enabled_by_default=True,
                    capabilities=["image_inference", "mask_generation"],
                    requires_context=["region", "crop_type", "task_type", "image_path"],
                    produces_artifacts=["inference_card"],
                ),
                handler=build_ktp_run_inference_workflow_handler(bundle=resolved_ktp_service_bundle),
            ),
            "ktp.trigger_training": ToolDefinition(
                spec=ToolSpecV2(
                    name="ktp.trigger_training",
                    display_name="触发训练",
                    description="Trigger the KTP training workflow through the service adapter boundary.",
                    visibility="bounded",
                    category="training",
                    pack_name="ktp",
                    usage_hint="Use when KTP needs to start a bounded training workflow instead of answering directly.",
                    input_schema={
                        "region": "string?",
                        "crop_type": "string?",
                        "task_type": "string?",
                        "query": "string",
                    },
                    safety_level="caution",
                    surface_visibility="web",
                    enabled_by_default=True,
                    capabilities=["training_trigger", "workflow_dispatch"],
                    requires_context=["region", "crop_type", "task_type"],
                    produces_artifacts=["training_card"],
                ),
                handler=build_ktp_trigger_training_handler(bundle=resolved_ktp_service_bundle),
            ),
            "ktp.build_report": ToolDefinition(
                spec=ToolSpecV2(
                    name="ktp.build_report",
                    display_name="生成报告",
                    description="Build a KTP report artifact by composing inference, retrieval, and confidence outputs.",
                    visibility="bounded",
                    category="report",
                    pack_name="ktp",
                    usage_hint="Use when the runtime needs a structured operator-facing report artifact from the KTP pack.",
                    input_schema={"query": "string", "region": "string", "crop_type": "string", "task_type": "string"},
                    safety_level="caution",
                    surface_visibility="web",
                    enabled_by_default=True,
                    capabilities=["report_generation", "operator_summary"],
                    requires_context=["region", "crop_type", "task_type", "query"],
                    produces_artifacts=["report_card"],
                ),
                handler=build_ktp_build_report_handler(bundle=resolved_ktp_service_bundle),
            ),
            "ktp.evaluate_confidence": ToolDefinition(
                spec=ToolSpecV2(
                    name="ktp.evaluate_confidence",
                    display_name="置信度评估",
                    description="Evaluate KTP workflow confidence using the pack's confidence service.",
                    visibility="bounded",
                    category="report",
                    pack_name="ktp",
                    usage_hint="Use when the runtime needs a confidence judgment instead of only raw inference output.",
                    input_schema={
                        "region": "string",
                        "crop_type": "string",
                        "task_type": "string",
                        "image_path": "string",
                    },
                    safety_level="caution",
                    surface_visibility="web",
                    enabled_by_default=True,
                    capabilities=["confidence_scoring", "quality_signal"],
                    requires_context=["region", "crop_type", "task_type", "image_path"],
                    produces_artifacts=["confidence_card"],
                ),
                handler=build_ktp_evaluate_confidence_handler(bundle=resolved_ktp_service_bundle),
            ),
            "ktp.build_visualization": ToolDefinition(
                spec=ToolSpecV2(
                    name="ktp.build_visualization",
                    display_name="生成可视化",
                    description="Build a KTP workflow visualization dashboard artifact.",
                    visibility="bounded",
                    category="visualization",
                    pack_name="ktp",
                    usage_hint="Use when the runtime should return a dashboard-style artifact for inspection or replay.",
                    input_schema={
                        "region": "string",
                        "crop_type": "string",
                        "task_type": "string",
                        "image_path": "string",
                    },
                    safety_level="caution",
                    surface_visibility="web",
                    enabled_by_default=True,
                    capabilities=["dashboard_generation", "artifact_packaging"],
                    requires_context=["region", "crop_type", "task_type", "image_path"],
                    produces_artifacts=["visualization_card"],
                ),
                handler=build_ktp_build_visualization_handler(bundle=resolved_ktp_service_bundle),
            ),
            "prosail.simulation": ToolDefinition(
                spec=ToolSpecV2(
                    name="prosail.simulation",
                    display_name="PROSAIL 光谱模拟",
                    description="Run PROSAIL leaf optical model to simulate vegetation spectral reflectance.",
                    visibility="public",
                    category="remote_sensing",
                    pack_name="prosail",
                    usage_hint="Use for vegetation spectral modeling when user asks about LAI inversion or needs spectral simulation.",
                    input_schema={
                        "N": "float?",
                        "Cab": "float?",
                        "Car": "float?",
                        "Cw": "float?",
                        "Cm": "float?",
                        "lai": "float?",
                        "tts": "float?",
                        "tto": "float?",
                        "psi": "float?",
                    },
                    safety_level="safe",
                    surface_visibility="web",
                    enabled_by_default=True,
                    capabilities=["spectral_simulation", "vegetation_modeling"],
                    produces_artifacts=["simulation_result"],
                ),
                handler=run_prosail_simulation,
            ),
            "prosail.build_lut": ToolDefinition(
                spec=ToolSpecV2(
                    name="prosail.build_lut",
                    display_name="PROSAIL 构建查找表",
                    description="Build a Lookup Table (LUT) for PROSAIL LAI inversion.",
                    visibility="public",
                    category="remote_sensing",
                    pack_name="prosail",
                    usage_hint="Use to build a LUT before performing LAI inversion.",
                    input_schema={
                        "params": "object?",
                        "output_path": "string?",
                    },
                    safety_level="safe",
                    surface_visibility="web",
                    enabled_by_default=True,
                    capabilities=["lut_building", "inversion_preparation"],
                    produces_artifacts=["lut_card"],
                ),
                handler=run_prosail_build_lut,
            ),
            "prosail.load_lut": ToolDefinition(
                spec=ToolSpecV2(
                    name="prosail.load_lut",
                    display_name="PROSAIL 加载查找表",
                    description="Load an existing PROSAIL Lookup Table (LUT) for LAI inversion.",
                    visibility="public",
                    category="remote_sensing",
                    pack_name="prosail",
                    usage_hint="Use to load a pre-built LUT before LAI inversion.",
                    input_schema={
                        "lut_path": "string",
                    },
                    safety_level="safe",
                    surface_visibility="web",
                    enabled_by_default=True,
                    capabilities=["lut_loading", "inversion_preparation"],
                    produces_artifacts=["lut_card"],
                ),
                handler=run_prosail_load_lut,
            ),
            "prosail.invert_lai": ToolDefinition(
                spec=ToolSpecV2(
                    name="prosail.invert_lai",
                    display_name="PROSAIL LAI 反演",
                    description="Invert Leaf Area Index (LAI) from reflectance data using PROSAIL model.",
                    visibility="public",
                    category="remote_sensing",
                    pack_name="prosail",
                    usage_hint="Use when user asks for LAI inversion or leaf area index estimation from vegetation indices.",
                    input_schema={
                        "reflectance": "object",
                        "lut_path": "string?",
                        "method": "string?",
                    },
                    safety_level="caution",
                    surface_visibility="web",
                    enabled_by_default=True,
                    capabilities=["lai_inversion", "vegetation_parameter_estimation"],
                    produces_artifacts=["inversion_result"],
                ),
                handler=run_prosail_invert_lai,
            ),
            "prosail.invert_lai_tif": ToolDefinition(
                spec=ToolSpecV2(
                    name="prosail.invert_lai_tif",
                    display_name="PROSAIL LAI 反演 (TIF→TIF)",
                    description="End-to-end LAI inversion from a GeoTIFF image file. Reads Sentinel-2 multi-band TIF, applies NDVI vegetation masking, performs PROSAIL LUT-based LAI inversion per pixel, and outputs LAI and confidence GeoTIFF files.",
                    visibility="public",
                    category="remote_sensing",
                    pack_name="prosail",
                    usage_hint="Use when user provides a TIF file and wants LAI inversion output as TIF. Requires at least 4 bands (B2/B3/B4/B8).",
                    input_schema={
                        "image_path": "string",
                        "lut_path": "string?",
                        "ndvi_threshold": "float?",
                        "scale_factor": "float?",
                        "method": "string?",
                        "output_dir": "string?",
                    },
                    safety_level="caution",
                    surface_visibility="web",
                    enabled_by_default=True,
                    capabilities=["lai_inversion", "vegetation_parameter_estimation", "geospatial_processing"],
                    produces_artifacts=["lai_geotiff", "lai_confidence_geotiff"],
                ),
                handler=run_prosail_invert_lai_tif,
            ),
            "apsim.crop_simulation": ToolDefinition(
                spec=ToolSpecV2(
                    name="apsim.crop_simulation",
                    display_name="APSIM 作物模拟",
                    description="使用 APSIM 作物生长模型进行作物模拟，支持多种作物（小麦、玉米、大豆等）和区域配置。",
                    visibility="public",
                    category="crop_simulation",
                    pack_name="apsim",
                    usage_hint="Use when the user asks for crop growth simulation, APSIM modeling, yield prediction, or crop phenology analysis.",
                    input_schema={
                        "crop_type": "string?",
                        "region": "string?",
                        "start_year": "integer?",
                        "end_year": "integer?",
                        "soil_type": "string?",
                        "sowing_date": "string?",
                        "cultivar": "string?",
                        "query": "string?",
                    },
                    safety_level="safe",
                    is_macro=False,
                    capabilities=["crop_simulation", "yield_prediction", "phenology_modeling"],
                    requires_context=["query"],
                    produces_artifacts=["simulation_data", "simulation_log"],
                ),
                handler=run_apsim_crop_simulation,
            ),
        }
    )
