from types import SimpleNamespace
import json
import os

import pytest

from runtime.apsim_example import ApsimExampleError, select_example, run_example
from schemas.analysis_workflow import planned_steps
from schemas.workspace import WorkspaceContext, WorkspaceIntent
from runtime.workspace_assistant import workspace_parts


def workflow(class_id=3, score=0.99, status="completed"):
    return SimpleNamespace(steps=[SimpleNamespace(step_id="crop", status=status,
        result={"predicted_class": {"class_id": class_id, "score": score}})])


@pytest.mark.parametrize("class_id,crop,model", [(0,"maize","Maize"),(2,"soybean","Soybean"),(3,"wheat","Wheat"),(4,"wheat","Wheat")])
def test_recognition_selects_matching_example(class_id, crop, model):
    selected, _ = select_example(workflow(class_id))
    assert selected[:2] == (crop, model)


@pytest.mark.parametrize("class_id,score,status", [(1,.99,"completed"),(5,.99,"completed"),(3,.4,"completed"),(3,.99,"failed")])
def test_unsupported_uncertain_or_incomplete_recognition_cannot_run(class_id, score, status):
    with pytest.raises(ApsimExampleError):
        select_example(workflow(class_id, score, status))


def test_example_dependency_does_not_require_lai_or_field_data():
    tasks, steps = planned_steps(["yield"], "apsim_example")
    assert tasks == ["crop", "yield"]
    assert steps[-1].depends_on == ["crop"]
    assert planned_steps(["yield"])[0] == ["crop", "lai", "yield"]


def test_assistant_uses_automatic_examples_and_preserves_field_mode():
    context = WorkspaceContext(workspace_id="test", revision=1, apsim_mode="example")
    _, parts = workspace_parts(WorkspaceIntent(intent="configure", task_ids=["yield"], summary="配置"), context, "plan")
    assert parts[0]["data"]["data_mode"] == "apsim_example"
    assert parts[0]["data"]["effective_task_ids"] == ["crop", "yield"]
    _, parts = workspace_parts(WorkspaceIntent(intent="configure", task_ids=["yield"], summary="配置", apsim_mode="field"), context, "plan")
    assert parts[0]["data"]["data_mode"] == "live"
    assert "lai" in parts[0]["data"]["effective_task_ids"]


def test_runner_executes_selected_model_and_reads_output(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    (root / "Examples/WeatherFiles").mkdir(parents=True)
    (root / "Examples/WeatherFiles/AU_Dalby.met").write_text("example weather")
    (root / "Models").write_text("binary")
    (root / "Examples/Maize.apsimx").write_text(json.dumps({"Children": [
        {"$type":"Models.Climate.Weather, Models", "FileName":"old.met"},
        {"$type":"Models.Clock, Models"}, {"$type":"Models.Report, Models"}]}))
    monkeypatch.setenv("APSIM_EXAMPLE_ROOT", str(root))
    monkeypatch.setenv("APSIM_EXAMPLE_MODELS_BIN", str(root / "Models"))
    output = tmp_path / "output"
    output.mkdir()
    (output / "Maize.Report.csv").write_text("Date,LAI,Biomass,GrainWt,Stage\n1990-01-01,9,9,900,9\n")

    def simulate(args, **kwargs):
        assert not (output / "Maize.Report.csv").exists()
        prepared = json.loads((output / "Maize.apsimx").read_text())
        assert prepared["Children"][0]["FileName"] == str((root / "Examples/WeatherFiles/AU_Dalby.met").resolve())
        assert "[Maize].LAI as LAI" in prepared["Children"][2]["VariableNames"]
        (output / "Maize.Report.csv").write_text("Date,LAI,Biomass,GrainWt,Stage\n1990-01-01,2,100,300,5\n")
        return SimpleNamespace(returncode=0, stdout="success", stderr="")

    monkeypatch.setattr("runtime.apsim_example.subprocess.run", simulate)
    result = run_example(workflow(0), output)
    assert result["apsim_executed"]
    assert result["example_yield_t_ha"] == 3.0
    assert result["input_provenance"]["template"] == "Maize.apsimx"
    assert "constrained_yield_t_ha" not in result
    assert "estimated_total_t" not in result


def test_example_report_contains_real_series_and_source_note(tmp_path):
    from runtime.apsim_example import register_example_report
    from runtime.artifact_store import ArtifactStore
    result = {"crop_label": "大豆", "example_yield_t_ha": 2.35,
        "timeseries": {"dates": ["1990-01-01", "1990-01-02"], "lai": [0, 2], "biomass": [0, 100], "grain_wt": [0, 235]},
        "input_provenance": {"template": "Soybean.apsimx", "weather": "AU_Dalby.met", "template_sha256": "a"*64, "weather_sha256": "b"*64}}
    register_example_report(ArtifactStore(db_path=str(tmp_path / "artifacts.sqlite3")), workflow=SimpleNamespace(workflow_id="example"), result=result, output_dir=tmp_path / "report")
    html = next((tmp_path / "report").glob("*.html")).read_text(encoding="utf-8")
    assert html.count("<polyline") == 3
    assert "不代表当前地块实际产量" in html
    assert "Soybean.apsimx" in html and "AU_Dalby.met" in html


@pytest.mark.skipif(not os.getenv("APSIM_EXAMPLE_MODELS_BIN"), reason="Requires installed Linux APSIM runtime")
@pytest.mark.parametrize("class_id,expected", [(3,"wheat"),(0,"maize"),(2,"soybean")])
def test_real_models_run_through_automatic_workflow_and_reports(tmp_path, class_id, expected):
    from runtime.analysis_workflow_store import AnalysisWorkflowStore
    from runtime.analysis_workflow_runner import _finish
    from runtime.artifact_store import ArtifactStore
    from schemas.analysis_workflow import CreateAnalysisWorkflowRequest
    from schemas.spatial import AoiGeometry, GeoJsonGeometry, ImageryCandidate
    store = AnalysisWorkflowStore(db_path=str(tmp_path / "workflow.sqlite3"))
    artifacts = ArtifactStore(db_path=str(tmp_path / "artifacts.sqlite3"))
    body = CreateAnalysisWorkflowRequest(data_mode="apsim_example", requested_task_ids=["yield"],
        aoi=AoiGeometry(geometry=GeoJsonGeometry(type="Polygon", coordinates=[[[100,38],[100.01,38],[100.01,38.01],[100,38]]])),
        imagery_item_id="isolated-recognition-fixture", imagery_snapshot=ImageryCandidate(item_id="isolated-recognition-fixture", collection="sentinel-2-l2a", acquired_at="2026-06-01"))
    item = store.create(body, owner_id="test")
    store.update_step(item.workflow_id, "imagery", owner_id="test", status="completed")
    store.update_step(item.workflow_id, "crop", owner_id="test", status="completed", result=workflow(class_id).steps[0].result)
    _finish(store, item.workflow_id, "test", artifact_root=tmp_path / "output", artifacts=artifacts)
    final = store.get(item.workflow_id, owner_id="test")
    assert final.status == "completed", final.model_dump()
    result = final.steps[-1].result
    assert result["apsim_executed"] and result["crop_type"] == expected
    assert len(result["timeseries"]["dates"]) == 730
    assert result["example_yield_t_ha"] > 0
    assert result["report_uri"] and final.report_uri
    assert "lai" not in final.effective_task_ids
