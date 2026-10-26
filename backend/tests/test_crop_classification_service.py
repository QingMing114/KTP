"""Crop classification service tests.

The service is the single implementation shared by the crop endpoint and the
analysis workflow. These tests pin the composition order and both imagery
input modes without running the spatial model.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from runtime.crop_classification import CropImagerySource, classify_crop


def _patch(monkeypatch, *, decision=None, report_references=None):
    calls: dict[str, object] = {}

    def fake_spatial(**kwargs):
        calls["spatial"] = kwargs
        return {"predicted_class": {"name": "maize"}, "class_scores": []}

    def fake_decide(provider, **kwargs):
        calls["decide"] = {"provider": provider, **kwargs}
        return decision

    def fake_register(store, **kwargs):
        calls["register"] = kwargs
        return report_references or {"report_uri": "artifact://r1"}

    monkeypatch.setattr("runtime.crop_classification.run_crop_spatial_analysis", fake_spatial)
    monkeypatch.setattr("runtime.crop_classification.decide_crop", fake_decide)
    monkeypatch.setattr("runtime.crop_classification.register_crop_report", fake_register)
    return calls


def _classify(tmp_path: Path, *, source, progress_callback=None, decision_progress=None, extra=None):
    return classify_crop(
        source=source,
        geometry={"type": "Polygon", "coordinates": []},
        observed_at="2026-05-14T00:00:00Z",
        farm_id="farm-1",
        area_hectares=12.5,
        output_dir=tmp_path,
        run_id="run-1",
        artifact_store=object(),
        imagery_item_id="item-1",
        provenance={"item_id": "item-1"},
        llm_provider=object(),
        progress_callback=progress_callback,
        decision_progress=decision_progress,
        extra_result_fields=extra,
    )


def test_reflectance_mode_passes_the_prepared_raster(monkeypatch, tmp_path):
    calls = _patch(monkeypatch)

    _classify(tmp_path, source=CropImagerySource(reflectance_path=tmp_path / "reflectance.tif"))

    spatial = calls["spatial"]
    assert spatial["reflectance_path"] == tmp_path / "reflectance.tif"
    assert spatial["item"] is None
    assert spatial["output_dir"] == tmp_path


def test_item_mode_passes_the_selected_item_and_geometry(monkeypatch, tmp_path):
    calls = _patch(monkeypatch)
    item = object()

    _classify(tmp_path, source=CropImagerySource(item=item))

    spatial = calls["spatial"]
    assert spatial["item"] is item
    assert spatial["reflectance_path"] is None
    assert spatial["geometry"] == {"type": "Polygon", "coordinates": []}


def test_decision_is_attached_and_provenance_is_recorded(monkeypatch, tmp_path):
    calls = _patch(monkeypatch, decision={"final_class_id": "maize"})

    outcome = _classify(tmp_path, source=CropImagerySource(item=object()))

    assert outcome.result["crop_decision"] == {"final_class_id": "maize"}
    assert outcome.result["imagery_provenance"] == {"item_id": "item-1"}
    assert calls["decide"]["observed_at"] == "2026-05-14T00:00:00Z"
    assert calls["decide"]["farm_id"] == "farm-1"


def test_report_references_are_merged_into_the_result(monkeypatch, tmp_path):
    _patch(monkeypatch, report_references={"report_uri": "artifact://r9", "report_version": "v3"})

    outcome = _classify(tmp_path, source=CropImagerySource(item=object()))

    assert outcome.report_references["report_uri"] == "artifact://r9"
    assert outcome.result["report_uri"] == "artifact://r9"
    assert outcome.result["report_version"] == "v3"


def test_extra_fields_reach_the_report_before_registration(monkeypatch, tmp_path):
    calls = _patch(monkeypatch)

    outcome = _classify(
        tmp_path,
        source=CropImagerySource(item=object()),
        extra={"shared_imagery_workflow_id": "wf-1"},
    )

    assert outcome.result["shared_imagery_workflow_id"] == "wf-1"
    assert calls["register"]["result"]["shared_imagery_workflow_id"] == "wf-1"


def test_decision_progress_runs_after_inference(monkeypatch, tmp_path):
    events: list[tuple[str, int]] = []
    _patch(monkeypatch, decision={"final_class_id": "maize"})

    _classify(
        tmp_path,
        source=CropImagerySource(item=object()),
        progress_callback=lambda detail, percent: events.append((detail, percent)),
        decision_progress=("正在判定", 97),
    )

    assert events == [("正在判定", 97)]


def test_decision_progress_is_skipped_without_a_callback(monkeypatch, tmp_path):
    _patch(monkeypatch, decision={"final_class_id": "maize"})

    outcome = _classify(
        tmp_path,
        source=CropImagerySource(item=object()),
        decision_progress=("正在判定", 97),
    )

    assert outcome.decision == {"final_class_id": "maize"}
