"""Registered tool wrapper for Sentinel-2 imagery search.

Search is read-only but interactive: in professional mode the user confirms the
date window and cloud limit before anything is searched. The tool therefore
stays host-invoked (``surface_visibility="debug"``) until the approval semantics
for interactive steps are wired into the tool pipeline; the endpoint uses it
today, so search has exactly one implementation.
"""

from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel, ConfigDict

from runtime.imagery_search import search_imagery
from schemas.runtime import ObservationV2, PackArtifactView, ToolPresentation, ToolSpecV2
from schemas.spatial import AoiGeometry, ImagerySearchRequest

IMAGERY_SEARCH_TOOL_NAME = "remote_sensing.imagery_search"
IMAGERY_SEARCH_TOOL_DISPLAY_NAME = "影像搜索"

ProgressCallback = Callable[[str, int], None]


class ImagerySearchToolInput(BaseModel):
    """JSON input for the imagery search tool."""

    model_config = ConfigDict(extra="forbid")

    aoi: AoiGeometry
    start_date: str | None = None
    end_date: str
    max_cloud_cover: float = 20
    collection: str = "sentinel-2-l2a"


def _presentation() -> ToolPresentation:
    return ToolPresentation(
        card_kind="search",
        summary_fields=["items", "search_id"],
        progress_phases=["查询 STAC 候选影像"],
        result_renderer="imagery_candidates",
    )


def build_imagery_search_tool_spec(
    *,
    available: bool,
    unavailable_reason: str | None = None,
    model_visible: bool = False,
) -> ToolSpecV2:
    """Build the tool spec; ``model_visible`` is the A5-style visibility gate."""
    return ToolSpecV2(
        name=IMAGERY_SEARCH_TOOL_NAME,
        display_name=IMAGERY_SEARCH_TOOL_DISPLAY_NAME,
        description=(
            "在指定 AOI 与时间窗内检索 Sentinel-2 L2A 候选影像，返回云量、覆盖率与推荐景，"
            "不下载影像。"
        ),
        visibility="bounded",
        category="remote_sensing",
        usage_hint=(
            "当需要为用户提供可选影像时使用；专业模式下应先由用户确认日期窗口与云量上限，"
            "且不产生任何下载或计算副作用。"
        ),
        input_schema=ImagerySearchToolInput.model_json_schema(),
        output_schema={
            "type": "object",
            "properties": {
                "items": {"type": "array"},
                "search_id": {"type": "string"},
            },
        },
        safety_level="safe",
        surface_visibility="all" if model_visible else "debug",
        enabled_by_default=True,
        permissions=[],
        produces_artifacts=[],
        availability="available" if available else "unavailable",
        unavailable_reason=None if available else (unavailable_reason or "imagery search is not configured"),
        presentation=_presentation(),
    )


def build_imagery_search_handler(
    *,
    provider_resolver: Callable[[], Any],
) -> Callable[..., tuple[ObservationV2, list[PackArtifactView]]]:
    """Bind the search implementation to a provider that may appear later."""

    def handler(
        *,
        progress_callback: ProgressCallback | None = None,
        **tool_input: Any,
    ) -> tuple[ObservationV2, list[PackArtifactView]]:
        payload = ImagerySearchToolInput.model_validate(tool_input)
        request = ImagerySearchRequest.model_validate(payload.model_dump())
        if progress_callback is not None:
            progress_callback("正在查询 STAC 候选影像", 10)
        outcome = search_imagery(provider_resolver(), request)
        if progress_callback is not None:
            progress_callback(f"候选影像已返回（{len(outcome.items)} 景）", 100)
        recommended = next((item for item in outcome.items if item.is_recommended), None)
        summary = f"找到 {len(outcome.items)} 景候选影像"
        if recommended is not None:
            summary += f"，推荐 {recommended.item_id}"
        observation = ObservationV2(
            source=IMAGERY_SEARCH_TOOL_NAME,
            status="success",
            summary=summary,
            payload={
                "items": [item.model_dump(mode="json") for item in outcome.items],
                "search_id": outcome.search_id,
            },
        )
        return observation, []

    return handler


def configure_imagery_search_tool(
    registry: Any,
    *,
    provider_resolver: Callable[[], Any],
    model_visible: bool = False,
) -> None:
    """(Re)register the imagery search tool on the host registry."""
    registry.register(
        IMAGERY_SEARCH_TOOL_NAME,
        build_imagery_search_tool_spec(available=True, model_visible=model_visible),
        build_imagery_search_handler(provider_resolver=provider_resolver),
    )


def register_unavailable_imagery_search_tool(registry: Any, *, reason: str | None = None) -> None:
    """Register the spec so discovery and availability reporting stay honest."""
    registry.register(
        IMAGERY_SEARCH_TOOL_NAME,
        build_imagery_search_tool_spec(available=False, unavailable_reason=reason),
        _unavailable_handler,
    )


def _unavailable_handler(**_kwargs: Any) -> tuple[ObservationV2, list[PackArtifactView]]:
    raise RuntimeError("imagery search tool is not configured")
