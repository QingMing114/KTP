"""Single implementation of the PROSAIL LAI inversion and report step.

Both the standalone ``POST /lai-analyses`` worker and the shared-imagery
workflow step call this module: run the inversion on an already-prepared
reflectance raster, validate the three produced files, register the artifacts,
and return the observation payload plus the artifact-id map.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from runtime.artifact_store import ArtifactStore
from v2.tools.lai_report_handler import run_lai_html_report

LAI_INVERSION_TOOL_NAME = "remote_sensing.lai_inversion"
REQUIRED_ARTIFACT_KINDS = ("lai_html_report", "lai_raster", "lai_preview")
REQUIRED_PAYLOAD_PATHS = ("report_path", "lai_raster_path", "lai_preview_path")


class LAIInversionError(RuntimeError):
    """Raised when the inversion succeeds but its outputs are incomplete."""


@dataclass(frozen=True)
class LAIInversionOutcome:
    """One completed inversion with its registered artifacts."""

    payload: dict[str, Any]
    artifact_ids: dict[str, str]


def run_lai_inversion(
    *,
    reflectance_path: Path,
    output_dir: Path,
    run_id: str,
    artifact_store: ArtifactStore,
    scene_constraints: dict[str, Any] | None = None,
    strict_scene_constraints: bool = False,
    pixel_progress_callback: Callable[[int, int], None] | None = None,
) -> LAIInversionOutcome:
    """Run the inversion, validate its outputs, and register its artifacts."""
    observation, views = run_lai_html_report(
        image_path=str(reflectance_path),
        artifact_output_dir=str(output_dir),
        progress_callback=pixel_progress_callback,
        scene_constraints=scene_constraints,
        **({"strict_scene_constraints": True} if strict_scene_constraints else {}),
    )
    if observation.status != "success":
        raise LAIInversionError(observation.summary or "LAI 反演失败")
    payload = dict(observation.payload or {})
    for key in REQUIRED_PAYLOAD_PATHS:
        value = payload.get(key)
        if not isinstance(value, str) or not Path(value).is_file():
            raise LAIInversionError(f"LAI 产物生成后未能通过文件校验: {key}")
    artifact_ids = {
        view.artifact_type: artifact_store.register(run_id, view) for view in views
    }
    missing = [kind for kind in REQUIRED_ARTIFACT_KINDS if kind not in artifact_ids]
    if missing:
        raise LAIInversionError(
            "LAI 分析产物生成后未能完整注册: " + ", ".join(missing)
        )
    return LAIInversionOutcome(payload=payload, artifact_ids=artifact_ids)
