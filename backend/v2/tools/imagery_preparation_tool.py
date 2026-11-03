"""Registered tool wrapper for AOI imagery preparation.

Preparation downloads bands and writes a shared raster, so it stays
host-invoked: the caller supplies the already-validated STAC item, the AOI, the
resolution, and the artifact store binding. The workflow step is the only
production entry today and invokes this tool through the registry.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field

from runtime.artifact_store import ArtifactStore
from runtime.imagery_preparation import (
    ARTIFACT_TYPE,
    DEFAULT_RESOLUTION_M,
    IMAGERY_PREPARATION_TOOL_NAME,
    prepare_imagery,
)
from schemas.runtime import ObservationV2, PackArtifactView, ToolPresentation, ToolSpecV2

IMAGERY_PREPARATION_TOOL_DISPLAY_NAME = "影像准备"

ProgressCallback = Callable[[str, int], None]


class ImageryPreparationToolInput(BaseModel):
    """JSON input for the imagery preparation tool."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    aoi_geometry: dict[str, Any]
    target_resolution_m: int = DEFAULT_RESOLUTION_M
    parameters: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    output_dir: str | None = None


def _presentation() -> ToolPresentation:
    return ToolPresentation(
        card_kind="geo",
        summary_fields=["artifact_id", "resolution_m", "bands"],
        progress_phases=["读取 Sentinel 波段", "重采样", "登记产物"],
        result_renderer="imagery_prepared",
    )


def build_imagery_preparation_tool_spec(
    *,
    available: bool,
    unavailable_reason: str | None = None,
    model_visible: bool = False,
) -> ToolSpecV2:
    """Build the tool spec; ``model_visible`` is the visibility gate."""
    return ToolSpecV2(
        name=IMAGERY_PREPARATION_TOOL_NAME,
        display_name=IMAGERY_PREPARATION_TOOL_DISPLAY_NAME,
        description=(
            "把已选 Sentinel-2 影像在指定 AOI 上裁剪并重采样为五波段共享反射率栅格，"
            "登记为后续作物识别与 LAI 复用的产物。"
        ),
        visibility="bounded",
        category="remote_sensing",
        usage_hint=(
            "当已有服务端签发的影像快照、且后续步骤需要共享反射率时使用；"
            "该操作会下载波段并写产物，不要为预览目的调用。"
        ),
        input_schema=ImageryPreparationToolInput.model_json_schema(),
        output_schema={
            "type": "object",
            "properties": {
                "artifact_id": {"type": "string"},
                "bands": {"type": "array"},
                "resolution_m": {"type": "integer"},
                "imagery_provenance": {"type": "object"},
            },
        },
        safety_level="caution",
        surface_visibility="all" if model_visible else "debug",
        enabled_by_default=True,
        permissions=["dataset:read", "artifact:write"],
        produces_artifacts=[ARTIFACT_TYPE],
        availability="available" if available else "unavailable",
        unavailable_reason=None
        if available
        else (unavailable_reason or "imagery preparation is not configured"),
        presentation=_presentation(),
    )


def build_imagery_preparation_handler(
    *,
    artifact_store: ArtifactStore,
    artifact_root: Path,
) -> Callable[..., tuple[ObservationV2, list[PackArtifactView]]]:
    """Bind the preparation implementation to one artifact store and root."""

    def handler(
        *,
        item: Any = None,
        progress_callback: ProgressCallback | None = None,
        **tool_input: Any,
    ) -> tuple[ObservationV2, list[PackArtifactView]]:
        payload = ImageryPreparationToolInput.model_validate(tool_input)
        if item is None:
            raise RuntimeError(
                "imagery preparation requires a host-resolved imagery item; it is not model-invokable yet"
            )
        output_dir = (
            Path(payload.output_dir)
            if payload.output_dir
            else artifact_root / "workflows" / payload.run_id
        )
        outcome = prepare_imagery(
            item=item,
            geometry=payload.aoi_geometry,
            output_dir=output_dir,
            run_id=payload.run_id,
            artifact_store=artifact_store,
            target_resolution_m=payload.target_resolution_m,
            parameters=payload.parameters,
            provenance=payload.provenance,
            progress_callback=progress_callback,
        )
        observation = ObservationV2(
            source=IMAGERY_PREPARATION_TOOL_NAME,
            status="success",
            summary=f"AOI 五波段影像已准备（{outcome.resolution_m}m），可供作物识别和 LAI 共用",
            payload=outcome.result,
        )
        return observation, []

    return handler


def configure_imagery_preparation_tool(
    registry: Any,
    *,
    artifact_store: ArtifactStore,
    artifact_root: Path,
    model_visible: bool = False,
) -> None:
    """(Re)register the preparation tool on the host registry."""
    registry.register(
        IMAGERY_PREPARATION_TOOL_NAME,
        build_imagery_preparation_tool_spec(available=True, model_visible=model_visible),
        build_imagery_preparation_handler(
            artifact_store=artifact_store,
            artifact_root=artifact_root,
        ),
    )


def register_unavailable_imagery_preparation_tool(
    registry: Any, *, reason: str | None = None
) -> None:
    """Register the spec so discovery and availability reporting stay honest."""
    registry.register(
        IMAGERY_PREPARATION_TOOL_NAME,
        build_imagery_preparation_tool_spec(available=False, unavailable_reason=reason),
        _unavailable_handler,
    )


def _unavailable_handler(**_kwargs: Any) -> tuple[ObservationV2, list[PackArtifactView]]:
    raise RuntimeError("imagery preparation tool is not configured")
