"""Single implementation of the crop-classification capability.

The standalone crop endpoint and the analysis workflow previously duplicated the
same sequence: spatial inference -> crop decision -> provenance -> report
registration. This module owns that sequence so every entry point (and, later,
the registered ``remote_sensing.crop_classification`` tool) shares one
implementation.

Both imagery inputs are supported because the two entries differ there:
the endpoint resolves a STAC item, while the workflow reuses the shared
reflectance raster produced by its imagery step.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from infra.imagery.crop_spatial import run_crop_spatial_analysis
from runtime.artifact_store import ArtifactStore
from runtime.crop_decision import decide_crop
from runtime.workflow_reports import register_crop_report

ProgressCallback = Callable[[str, int], None]


@dataclass(frozen=True)
class CropImagerySource:
    """The imagery a classification runs on: a selected item or a prepared raster."""

    item: Any | None = None
    reflectance_path: Path | None = None


@dataclass(frozen=True)
class CropClassificationOutcome:
    """One completed classification."""

    result: dict[str, Any]
    decision: dict[str, Any] | None
    report_references: dict[str, str]


def classify_crop(
    *,
    source: CropImagerySource,
    geometry: dict[str, Any] | None,
    observed_at: str,
    farm_id: str | None,
    area_hectares: float | None,
    output_dir: Path,
    run_id: str,
    artifact_store: ArtifactStore,
    imagery_item_id: str,
    provenance: dict[str, Any],
    llm_provider: Any = None,
    progress_callback: ProgressCallback | None = None,
    decision_progress: tuple[str, int] | None = None,
    extra_result_fields: dict[str, Any] | None = None,
) -> CropClassificationOutcome:
    """Run spatial inference, decide the crop, and register the report.

    ``decision_progress`` lets the workflow report the decision stage without
    changing the endpoint's progress sequence.
    """
    result = run_crop_spatial_analysis(
        item=source.item,
        geometry=geometry,
        output_dir=output_dir,
        reflectance_path=source.reflectance_path,
        progress_callback=progress_callback,
    )

    if decision_progress is not None and progress_callback is not None:
        progress_callback(*decision_progress)

    decision = decide_crop(
        llm_provider,
        model_result=result,
        observed_at=observed_at,
        farm_id=farm_id,
        geometry=geometry,
        area_hectares=area_hectares,
    )
    if decision is not None:
        result["crop_decision"] = decision
    result["imagery_provenance"] = provenance
    if extra_result_fields:
        result.update(extra_result_fields)

    report_references = register_crop_report(
        artifact_store,
        run_id=run_id,
        output_dir=output_dir,
        imagery_item_id=imagery_item_id,
        observed_at=observed_at,
        area_hectares=area_hectares,
        result=result,
    )
    result.update(report_references)

    return CropClassificationOutcome(
        result=result,
        decision=decision,
        report_references=report_references,
    )
