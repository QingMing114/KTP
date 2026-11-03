"""Registered tool wrapper for PROSAIL LAI inversion.

Inversion is expensive and needs an already-prepared reflectance raster, so the
tool is host-invoked: the caller supplies the raster path and the output
directory. Both production entries (the standalone analysis worker and the
workflow step) invoke it through the registry.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field

from runtime.artifact_store import ArtifactStore
from runtime.lai_inversion import (
    LAI_INVERSION_TOOL_NAME,
    REQUIRED_ARTIFACT_KINDS,
    run_lai_inversion,
)
from schemas.runtime import ObservationV2, PackArtifactView, ToolPresentation, ToolSpecV2

LAI_INVERSION_TOOL_DISPLAY_NAME = "LAI 反演"

ProgressCallback = Callable[[str, int], None]
PixelProgressCallback = Callable[[int, int], None]


class LAIInversionToolInput(BaseModel):
    """JSON input for the LAI inversion tool."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    reflectance_path: str
    output_dir: str
    scene_constraints: dict[str, Any] | None = None
    strict_scene_constraints: bool = False


def _presentation() -> ToolPresentation:
    return ToolPresentation(
        card_kind="analysis",
        summary_fields=["result.lai_mean", "result.quality.valid_pixel_fraction"],
        progress_phases=["读取反射率", "PROSAIL 反演", "生成报告"],
        result_renderer="lai_report",
    )


def build_lai_inversion_tool_spec(
    *,
    available: bool,
    unavailable_reason: str | None = None,
    model_visible: bool = False,
) -> ToolSpecV2:
    """Build the tool spec; ``model_visible`` is the visibility gate."""
    return ToolSpecV2(
        name=LAI_INVERSION_TOOL_NAME,
        display_name=LAI_INVERSION_TOOL_DISPLAY_NAME,
        description=(
            "在已准备好的五波段反射率栅格上执行 PROSAIL LAI 反演，产出 LAI 栅格、"
            "预览图与自包含 HTML 报告。"
        ),
        visibility="bounded",
        category="remote_sensing",
        usage_hint=(
            "当共享反射率已就绪且需要叶面积指数时使用；反演耗时较长，"
            "只有共享影像已准备时才复用本工具。"
        ),
        input_schema=LAIInversionToolInput.model_json_schema(),
        output_schema={
            "type": "object",
            "properties": {
                "result": {"type": "object"},
                "artifact_ids": {"type": "object"},
            },
        },
        safety_level="caution",
        surface_visibility="all" if model_visible else "debug",
        enabled_by_default=True,
        permissions=["dataset:read", "artifact:write"],
        produces_artifacts=list(REQUIRED_ARTIFACT_KINDS),
        availability="available" if available else "unavailable",
        unavailable_reason=None
        if available
        else (unavailable_reason or "LAI inversion tool is not configured"),
        presentation=_presentation(),
    )


def build_lai_inversion_handler(
    *,
    artifact_store: ArtifactStore,
) -> Callable[..., tuple[ObservationV2, list[PackArtifactView]]]:
    """Bind the inversion implementation to one artifact store."""

    def handler(
        *,
        pixel_progress_callback: PixelProgressCallback | None = None,
        progress_callback: ProgressCallback | None = None,
        **tool_input: Any,
    ) -> tuple[ObservationV2, list[PackArtifactView]]:
        payload = LAIInversionToolInput.model_validate(tool_input)
        pixel_callback = pixel_progress_callback
        if pixel_callback is None and progress_callback is not None:
            def pixel_callback(processed: int, total: int) -> None:
                percent = min(95, 10 + round(80 * processed / max(total, 1)))
                progress_callback(f"PROSAIL 已反演 {processed:,} / {total:,} 个有效像元", percent)
        outcome = run_lai_inversion(
            reflectance_path=Path(payload.reflectance_path),
            output_dir=Path(payload.output_dir),
            run_id=payload.run_id,
            artifact_store=artifact_store,
            scene_constraints=payload.scene_constraints,
            strict_scene_constraints=payload.strict_scene_constraints,
            pixel_progress_callback=pixel_callback,
        )
        if progress_callback is not None:
            progress_callback("LAI 反演报告已生成", 100)
        observation = ObservationV2(
            source=LAI_INVERSION_TOOL_NAME,
            status="success",
            summary=f"LAI 反演完成（均值 {outcome.payload.get('lai_mean')}）",
            payload={"result": outcome.payload, "artifact_ids": outcome.artifact_ids},
        )
        return observation, []

    return handler


def configure_lai_inversion_tool(
    registry: Any,
    *,
    artifact_store: ArtifactStore,
    model_visible: bool = False,
) -> None:
    """(Re)register the inversion tool on the host registry."""
    registry.register(
        LAI_INVERSION_TOOL_NAME,
        build_lai_inversion_tool_spec(available=True, model_visible=model_visible),
        build_lai_inversion_handler(artifact_store=artifact_store),
    )


def register_unavailable_lai_inversion_tool(
    registry: Any, *, reason: str | None = None
) -> None:
    """Register the spec so discovery and availability reporting stay honest."""
    registry.register(
        LAI_INVERSION_TOOL_NAME,
        build_lai_inversion_tool_spec(available=False, unavailable_reason=reason),
        _unavailable_handler,
    )


def _unavailable_handler(**_kwargs: Any) -> tuple[ObservationV2, list[PackArtifactView]]:
    raise RuntimeError("LAI inversion tool is not configured")
