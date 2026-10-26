"""Model-facing tool wrapper for crop classification.

The capability itself lives in :mod:`runtime.crop_classification`; this module
declares it as a registered tool so host entries can invoke the same
implementation through the tool registry with one spec, one availability rule
and one handler.

The tool stays ``surface_visibility="debug"``: the endpoint uses it today, but
the planner is not offered it until interactive confirmation semantics are
settled. It is host-invoked, so the caller supplies the already-validated STAC
item rather than an opaque snapshot the model could forge.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field

from runtime.artifact_store import ArtifactStore
from runtime.crop_classification import CropImagerySource, classify_crop, crop_step_detail
from schemas.runtime import ObservationV2, PackArtifactView, ToolPresentation, ToolSpecV2

CROP_TOOL_NAME = "remote_sensing.crop_classification"
CROP_TOOL_DISPLAY_NAME = "作物识别"

ProgressCallback = Callable[[str, int], None]


class CropToolInput(BaseModel):
    """JSON input for the crop tool (the resolved imagery item is a host argument)."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    imagery_item_id: str = Field(min_length=1)
    imagery_snapshot: dict[str, Any]
    aoi_geometry: dict[str, Any]
    area_hectares: float | None = None
    farm_id: str | None = None
    observed_at: str = Field(min_length=1)
    output_dir: str | None = None


def _presentation() -> ToolPresentation:
    return ToolPresentation(
        card_kind="analysis",
        summary_fields=["crop_decision.final_name_zh", "predicted_class.score"],
        progress_phases=["准备影像", "模型推理", "生成判定", "写报告"],
        result_renderer="crop_decision",
    )


def build_crop_tool_spec(
    *,
    available: bool,
    unavailable_reason: str | None = None,
    model_visible: bool = False,
) -> ToolSpecV2:
    """Build the tool spec; unconfigured deployments report ``unavailable``.

    ``model_visible`` is the A5 gate: the planner only sees the tool when the
    deployment explicitly enables it, because the tool needs a host-resolved
    imagery item that a model cannot supply on its own.
    """
    return ToolSpecV2(
        name=CROP_TOOL_NAME,
        display_name=CROP_TOOL_DISPLAY_NAME,
        description=(
            "在已校验的 Sentinel-2 影像与 AOI 上执行作物识别：输出六类模型分数、"
            "结合地点与时序的作物判定，并登记识别报告。"
        ),
        visibility="bounded",
        category="remote_sensing",
        usage_hint=(
            "当运行方已有服务端签发的影像快照并需要作物识别结果时使用；"
            "没有快照时先完成影像搜索与选片。"
        ),
        input_schema=CropToolInput.model_json_schema(),
        output_schema={
            "type": "object",
            "properties": {
                "crop_decision": {"type": ["object", "null"]},
                "predicted_class": {"type": "object"},
                "class_scores": {"type": "array"},
            },
        },
        safety_level="caution",
        surface_visibility="all" if model_visible else "debug",
        enabled_by_default=True,
        permissions=["dataset:read", "artifact:write"],
        produces_artifacts=["crop_classification_report"],
        availability="available" if available else "unavailable",
        unavailable_reason=None if available else (unavailable_reason or "crop tool is not configured"),
        presentation=_presentation(),
    )


def build_crop_handler(
    *,
    artifact_store: ArtifactStore,
    artifact_root: Path,
    llm_provider: Any = None,
    llm_provider_resolver: Callable[[], Any] | None = None,
) -> Callable[..., tuple[ObservationV2, list[PackArtifactView]]]:
    """Bind the classification implementation to one artifact store and root.

    ``llm_provider_resolver`` is evaluated per call so a host that attaches its
    engine after installation still gets the current provider.
    """

    def handler(
        *,
        item: Any = None,
        progress_callback: ProgressCallback | None = None,
        **tool_input: Any,
    ) -> tuple[ObservationV2, list[PackArtifactView]]:
        payload = CropToolInput.model_validate(tool_input)
        if item is None:
            raise RuntimeError(
                "crop tool requires a host-resolved imagery item; it is not model-invokable yet"
            )
        snapshot = payload.imagery_snapshot
        output_dir = (
            Path(payload.output_dir)
            if payload.output_dir
            else artifact_root / "crop" / payload.run_id
        )
        resolved_llm = llm_provider_resolver() if llm_provider_resolver is not None else llm_provider
        outcome = classify_crop(
            source=CropImagerySource(item=item),
            geometry=payload.aoi_geometry,
            observed_at=payload.observed_at,
            farm_id=payload.farm_id,
            area_hectares=payload.area_hectares,
            output_dir=output_dir,
            run_id=payload.run_id,
            artifact_store=artifact_store,
            imagery_item_id=payload.imagery_item_id,
            provenance={
                "item_id": snapshot.get("item_id", payload.imagery_item_id),
                "collection": snapshot.get("collection"),
                "acquired_at": snapshot.get("acquired_at", payload.observed_at),
                "cloud_cover": snapshot.get("cloud_cover"),
                "asset_fingerprint": snapshot.get("asset_fingerprint"),
            },
            llm_provider=resolved_llm,
            progress_callback=progress_callback,
        )
        observation = ObservationV2(
            source=CROP_TOOL_NAME,
            status="success",
            summary=crop_step_detail(outcome.decision),
            payload=outcome.result,
        )
        return observation, []

    return handler


def configure_crop_tool(
    registry: Any,
    *,
    artifact_store: ArtifactStore,
    artifact_root: Path,
    llm_provider: Any = None,
    llm_provider_resolver: Callable[[], Any] | None = None,
    model_visible: bool = False,
) -> None:
    """(Re)register the crop tool once the product artifact store exists."""
    registry.register(
        CROP_TOOL_NAME,
        build_crop_tool_spec(available=True, model_visible=model_visible),
        build_crop_handler(
            artifact_store=artifact_store,
            artifact_root=artifact_root,
            llm_provider=llm_provider,
            llm_provider_resolver=llm_provider_resolver,
        ),
    )


def register_unavailable_crop_tool(registry: Any, *, reason: str | None = None) -> None:
    """Register the spec so discovery and availability reporting stay honest."""
    registry.register(
        CROP_TOOL_NAME,
        build_crop_tool_spec(available=False, unavailable_reason=reason),
        _unavailable_handler,
    )


def _unavailable_handler(**_kwargs: Any) -> tuple[ObservationV2, list[PackArtifactView]]:
    raise RuntimeError("crop tool is not configured")
