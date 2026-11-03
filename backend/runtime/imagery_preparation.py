"""Single implementation of AOI imagery preparation.

Given a selected STAC item and an AOI, read the five PROSAIL bands, resample to
the workflow resolution, register the shared reflectance artifact, and return
the exact step result payload. The workflow step and the registered tool both
call this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from infra.imagery.aoi_band_reader import read_prosail_reflectance_aoi
from runtime.artifact_store import ArtifactStore
from schemas.spatial import PROSAIL_REFLECTANCE_BANDS

ARTIFACT_TYPE = "reflectance_tif"
ARTIFACT_TITLE = "共享 AOI Sentinel 反射率"
DEFAULT_RESOLUTION_M = 20
IMAGERY_PREPARATION_TOOL_NAME = "remote_sensing.imagery_preparation"

ProgressCallback = Callable[[str, int], None]


@dataclass(frozen=True)
class ImageryPreparationOutcome:
    """One prepared shared reflectance artifact."""

    reflectance_path: Path
    artifact_id: str
    bands: list[str]
    resolution_m: int
    result: dict[str, Any]


def prepare_imagery(
    *,
    item: Any,
    geometry: dict[str, Any],
    output_dir: Path,
    run_id: str,
    artifact_store: ArtifactStore,
    target_resolution_m: int = DEFAULT_RESOLUTION_M,
    parameters: dict[str, Any] | None = None,
    provenance: dict[str, Any] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> ImageryPreparationOutcome:
    """Read the shared AOI reflectance raster and register it as an artifact."""
    output_dir.mkdir(parents=True, exist_ok=True)
    reflectance = output_dir / "reflectance.tif"
    read_prosail_reflectance_aoi(
        item=item,
        geometry=geometry,
        output_path=reflectance,
        target_resolution_m=target_resolution_m,
        progress_callback=progress_callback,
    )
    artifact_id = artifact_store.register(
        run_id,
        SimpleNamespace(
            pack_name="sentinel",
            artifact_type=ARTIFACT_TYPE,
            title=ARTIFACT_TITLE,
            uri=str(reflectance),
            content=None,
        ),
    )
    bands = list(PROSAIL_REFLECTANCE_BANDS)
    result = {
        "artifact_id": artifact_id,
        "bands": bands,
        "resolution_m": target_resolution_m,
        "parameters": dict(parameters or {}),
        "imagery_provenance": dict(provenance or {}),
    }
    return ImageryPreparationOutcome(
        reflectance_path=reflectance,
        artifact_id=artifact_id,
        bands=bands,
        resolution_m=target_resolution_m,
        result=result,
    )
