"""HTML dashboard builder for workflow visualization."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

from shared.presentation import (
    display_bool,
    display_confidence_label,
    display_crop_type,
    display_region,
    display_status,
    display_task_type,
    localize_runtime_text,
)
from services.visualization_service.config import (
    VisualizationServiceConfig,
    get_visualization_service_config,
)
from services.visualization_service.previews import (
    build_artifact_preview,
    build_class_palette,
    color_to_hex,
)
from services.visualization_service.schemas import (
    VisualizationArtifact,
    VisualizationRequest,
    VisualizationResult,
)


class VisualizationBuilder:
    """Build a self-contained HTML dashboard from one workflow run."""

    def __init__(self, config: VisualizationServiceConfig | None = None) -> None:
        self._config = config or get_visualization_service_config()
        self._environment = Environment(
            loader=FileSystemLoader(self._config.visualization_template_dir),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._environment.filters["to_pretty_json"] = self._to_pretty_json

    def build_dashboard(self, request: VisualizationRequest) -> VisualizationResult:
        """Render a dashboard HTML document and persist derived artifacts."""
        try:
            template = self._environment.get_template("dashboard.html.j2")
        except TemplateNotFound as exc:
            raise FileNotFoundError(
                f"visualization template not found in {self._config.visualization_template_dir}"
            ) from exc

        request_dir = Path(self._config.visualization_output_dir) / request.request_id
        request_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = request_dir / "workflow_snapshot.json"
        dashboard_path = request_dir / "dashboard.html"

        snapshot_path.write_text(
            self._to_pretty_json(request.final_state),
            encoding="utf-8",
        )

        artifacts, inline_previews = self._build_artifacts(request=request, output_dir=request_dir)
        warnings = self._collect_warnings(request=request)
        sections = self._build_sections(request=request, artifacts=artifacts)
        stage_cards = self._build_stage_cards(request)
        model_metric_cards = self._build_model_metric_cards(request)
        class_legend = self._build_class_legend(request)
        embedded_report_html = self._load_report_html(request)
        display = self._build_display_context(request)

        generated_at = datetime.now(timezone.utc)
        title = display["title"]
        html = template.render(
            request=request,
            title=title,
            generated_at=generated_at.isoformat(),
            artifacts=artifacts,
            inline_previews=inline_previews,
            warnings=warnings,
            sections=sections,
            stage_cards=stage_cards,
            model_metric_cards=model_metric_cards,
            class_legend=class_legend,
            embedded_report_html=embedded_report_html,
            display=display,
            request_json=self._to_pretty_json(
                {
                    "request_id": request.request_id,
                    "user_query": request.user_query,
                    "task_type": request.task_type,
                    "region": request.region,
                    "crop_type": request.crop_type,
                    "image_path": request.image_path,
                    "use_mock": request.use_mock,
                    "extra_params": request.extra_params,
                }
            ),
            final_state_json=self._to_pretty_json(request.final_state),
        )
        dashboard_path.write_text(html, encoding="utf-8")

        return VisualizationResult(
            visualization_id=f"viz-{request.request_id}",
            title=title,
            dashboard_path=str(dashboard_path),
            artifact_dir=str(request_dir),
            snapshot_path=str(snapshot_path),
            generated_at=generated_at,
            sections=sections,
            artifacts=artifacts,
            html=html if self._config.visualization_embed_html_in_response else None,
        )

    def _build_artifacts(
        self,
        *,
        request: VisualizationRequest,
        output_dir: Path,
    ) -> tuple[list[VisualizationArtifact], dict[str, str]]:
        artifacts: list[VisualizationArtifact] = []
        inline_previews: dict[str, str] = {}
        artifact_inputs = [
            ("input_image", "输入图像", "input_image", request.image_path),
            (
                "raw_prediction",
                "原始预测",
                "class_map",
                self._get_inference_value(request, "raw_prediction_uri"),
            ),
            (
                "target_mask",
                "目标掩膜",
                "mask",
                self._get_inference_value(request, "mask_uri"),
            ),
            (
                "confidence_map",
                "置信度图",
                "confidence_map",
                self._get_inference_value(request, "confidence_map_uri"),
            ),
        ]
        for artifact_key, title, artifact_kind, source_uri in artifact_inputs:
            artifact, data_uri = build_artifact_preview(
                artifact_key=artifact_key,
                title=title,
                artifact_kind=artifact_kind,
                source_uri=source_uri,
                output_dir=output_dir,
            )
            artifacts.append(artifact)
            if data_uri:
                inline_previews[artifact_key] = data_uri

        report_uri = self._get_report_value(request, "report_uri")
        artifacts.append(
            VisualizationArtifact(
                artifact_key="report",
                title="生成报告",
                artifact_kind="html_report",
                source_uri=report_uri,
                preview_uri=None,
                available=bool(report_uri and Path(str(report_uri)).expanduser().exists()),
                note=None if report_uri else "未生成报告",
            )
        )
        return artifacts, inline_previews

    @staticmethod
    def _build_sections(
        *,
        request: VisualizationRequest,
        artifacts: list[VisualizationArtifact],
    ) -> list[str]:
        sections = ["overview", "timeline", "artifacts", "request"]
        if any(artifact.available for artifact in artifacts):
            sections.append("outputs")
        if request.inference_result is not None:
            sections.append("inference")
        if request.rag_result is not None:
            sections.append("rag")
        if request.report_result is not None:
            sections.append("report")
        if request.confidence_result is not None:
            sections.append("confidence")
        sections.append("raw_state")
        return sections

    @staticmethod
    def _build_stage_cards(request: VisualizationRequest) -> list[dict[str, str]]:
        timing_lookup = {
            item.get("stage"): item
            for item in request.stage_timings
            if isinstance(item, dict) and item.get("stage")
        }
        base_cards = [
            {
                "label": "请求解析",
                "stage": "parse_request",
                "status": "done" if request.planner_result is not None else "missing",
                "detail": display_task_type(request.task_type, default="未解析", include_raw=True),
            },
            {
                "label": "模型注册表查询",
                "stage": "check_model_registry",
                "status": "done" if request.model_exists is not None else "missing",
                "detail": "已找到可用模型" if request.model_exists else "进入训练分支",
            },
            {
                "label": "训练触发",
                "stage": "trigger_training",
                "status": "triggered" if request.training_triggered else "skipped",
                "detail": request.training_backend or "无需训练",
            },
            {
                "label": "推理",
                "stage": "run_inference",
                "status": "done" if request.inference_result is not None else "skipped",
                "detail": str(request.model_version or "未生成推理结果"),
            },
            {
                "label": "知识检索",
                "stage": "run_rag",
                "status": "done" if request.rag_result is not None else "skipped",
                "detail": f"{len((request.rag_result or {}).get('sources', []))} 条来源",
            },
            {
                "label": "报告生成",
                "stage": "build_report",
                "status": "done" if request.report_result is not None else "skipped",
                "detail": str((request.report_result or {}).get("report_uri", "未生成报告")),
            },
            {
                "label": "置信度评估",
                "stage": "evaluate_confidence",
                "status": "done" if request.confidence_result is not None else "skipped",
                "detail": display_confidence_label(
                    (request.confidence_result or {}).get("final_label"),
                ),
            },
            {
                "label": "可视化生成",
                "stage": "build_visualization",
                "status": "done",
                "detail": display_status(request.workflow_status),
            },
        ]
        cards: list[dict[str, str]] = []
        for card in base_cards:
            timing = timing_lookup.get(card["stage"], {})
            duration_ms = timing.get("duration_ms")
            raw_status = str(timing.get("status", card["status"]))
            raw_detail = str(timing.get("detail", card["detail"]))
            cards.append(
                {
                    "label": str(card["label"]),
                    "status_class": VisualizationBuilder._normalize_status_class(raw_status),
                    "status_label": display_status(raw_status),
                    "detail": VisualizationBuilder._localize_stage_detail(
                        stage=str(card["stage"]),
                        detail=raw_detail,
                    ),
                    "duration_label": (
                        f"{float(duration_ms):.2f} ms"
                        if isinstance(duration_ms, (int, float))
                        else "未提供"
                    ),
                }
            )
        return cards

    @staticmethod
    def _build_model_metric_cards(request: VisualizationRequest) -> list[dict[str, str]]:
        metrics = request.model_metrics or {}
        label_map = {
            "miou": "mIoU",
            "source": "来源",
        }
        cards: list[dict[str, str]] = []
        for key, value in metrics.items():
            label = label_map.get(str(key).lower(), str(key))
            if isinstance(value, (str, int, float, bool)):
                cards.append({"label": label, "value": str(value)})
            elif isinstance(value, list) and value and all(
                isinstance(item, (str, int, float, bool)) for item in value
            ):
                cards.append({"label": label, "value": ", ".join(str(item) for item in value)})
        return cards[:8]

    @staticmethod
    def _build_class_legend(request: VisualizationRequest) -> list[dict[str, str | bool]]:
        inference = request.inference_result or {}
        class_labels = {
            int(key): str(value)
            for key, value in (inference.get("class_labels") or {}).items()
        }
        distribution = inference.get("class_distribution") or []
        class_values = sorted(
            {
                *class_labels.keys(),
                *[
                    int(item.get("class_value"))
                    for item in distribution
                    if isinstance(item, dict) and item.get("class_value") is not None
                ],
            }
        )
        if not class_values:
            return []
        palette = build_class_palette(class_values)
        target_classes = {int(item) for item in inference.get("target_classes", [])}
        distribution_lookup = {
            int(item.get("class_value")): item
            for item in distribution
            if isinstance(item, dict) and item.get("class_value") is not None
        }
        legend: list[dict[str, str | bool]] = []
        for class_value in class_values:
            dist = distribution_lookup.get(class_value, {})
            legend.append(
                {
                    "class_value": str(class_value),
                    "label": class_labels.get(class_value, f"类别_{class_value}"),
                    "color_hex": color_to_hex(palette.get(class_value, (128, 128, 128))),
                    "target": class_value in target_classes,
                    "count": str(dist.get("count", "未提供")),
                    "ratio": str(dist.get("ratio", "未提供")),
                }
            )
        return legend

    @staticmethod
    def _load_report_html(request: VisualizationRequest) -> str | None:
        report_result = request.report_result or {}
        inline_html = report_result.get("html")
        if isinstance(inline_html, str) and inline_html.strip():
            return inline_html
        report_uri = report_result.get("report_uri")
        if not report_uri:
            return None
        report_path = Path(str(report_uri)).expanduser()
        if not report_path.exists():
            return None
        return report_path.read_text(encoding="utf-8")

    @staticmethod
    def _collect_warnings(request: VisualizationRequest) -> list[str]:
        warnings: list[str] = []
        warnings.extend(str(item) for item in request.errors)
        warnings.extend(str(item) for item in (request.inference_result or {}).get("warnings", []))
        warnings.extend(
            str(item)
            for item in (request.confidence_result or {}).get("image_detail", {}).get("warnings", [])
        )
        return list(dict.fromkeys(localize_runtime_text(item) for item in warnings if item))

    @staticmethod
    def _get_inference_value(request: VisualizationRequest, key: str) -> str | None:
        if request.inference_result is None:
            return None
        value = request.inference_result.get(key)
        return str(value) if value is not None else None

    @staticmethod
    def _get_report_value(request: VisualizationRequest, key: str) -> str | None:
        if request.report_result is None:
            return None
        value = request.report_result.get(key)
        return str(value) if value is not None else None

    @staticmethod
    def _to_pretty_json(payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)

    @staticmethod
    def _build_display_context(request: VisualizationRequest) -> dict[str, str]:
        return {
            "title": f"{display_task_type(request.task_type, default='工作流', include_raw=False)}工作流看板",
            "workflow_status": display_status(request.workflow_status),
            "task_type": display_task_type(request.task_type, include_raw=True),
            "region": display_region(request.region, include_raw=True),
            "crop_type": display_crop_type(request.crop_type, include_raw=True),
            "use_mock": display_bool(request.use_mock),
        }

    @staticmethod
    def _normalize_status_class(status: str) -> str:
        normalized = status.strip().lower()
        if normalized in {"done", "completed", "success"}:
            return "done"
        if normalized in {"triggered", "started", "running"}:
            return "triggered"
        if normalized == "failed":
            return "failed"
        if normalized == "missing":
            return "missing"
        return "skipped"

    @staticmethod
    def _localize_stage_detail(*, stage: str, detail: str) -> str:
        normalized_stage = stage.strip().lower()
        normalized_detail = detail.strip()
        if normalized_stage == "parse_request":
            return display_task_type(normalized_detail, default="未解析", include_raw=True)
        if normalized_stage == "run_rag":
            return localize_runtime_text(normalized_detail)
        if normalized_stage == "evaluate_confidence":
            return display_confidence_label(normalized_detail)
        if normalized_stage == "build_visualization":
            return display_status(normalized_detail)
        return localize_runtime_text(normalized_detail)
