"""Verified field sources, dated LAI and scenario output must agree."""

import csv
import hashlib
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

from runtime.apsim_field_dataset import FieldDatasetError, load_field_dataset
from runtime.apsim_field_runner import ApsimFieldError, _constrain_scenarios, _read_daily_report
from runtime.analysis_workflow_runner import _finish
from runtime.yield_input_assessment import assess_yield_inputs
from schemas.analysis_workflow import YieldAgronomicInputs, YieldInputAssessment

from test_yield_input_assessment import _workflow


def _source(root: Path, name: str, content: str) -> dict:
    path = root / name
    path.write_text(content, encoding="utf-8")
    return {"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "source": f"test:{name}", "status": "verified"}


def _catalog(tmp_path, monkeypatch):
    root = tmp_path / "catalog" / "field-1"
    root.mkdir(parents=True)
    days = [date(2026, 5, 1) + timedelta(days=i) for i in range(183)]
    met = "[weather.met.weather]\nlatitude = 38.005\nlongitude = 100.005\n"
    met += "year day radn maxt mint rain\n() () (MJ/m2) (oC) (oC) (mm)\n"
    met += "\n".join(f"{day.year} {day.timetuple().tm_yday} 18 25 10 0" for day in days)
    template = json.dumps({"Children": [{"Name": "Weather", "$type": "Models.Climate.Weather, Models"},
                                        {"Name": "Report", "$type": "Models.Report, Models",
                                         "VariableNames": ["[Clock].Today", "[Wheat].LAI", "[Wheat].Grain.Total.Wt*10 as Yield"],
                                         "EventNames": ["[Wheat].Harvesting"]}]})
    manifest = {
        "dataset_id": "field-1", "status": "verified", "verified_by": "test-fixture",
        "crop_type": "wheat", "cultivar": "cultivar-1", "sowing_date": "2026-05-01",
        "season_end": "2026-10-30", "field_center_lonlat": [100.005, 38.005],
        "weather": _source(root, "weather.met", met),
        "soil": _source(root, "soil.json", "{\"measured\": true}"),
        "management": _source(root, "management.json", "{\"sowing\": \"2026-05-01\"}"),
        "scenarios": [{"id": scenario, **_source(root, f"{scenario}.apsimx", template)}
                      for scenario in ("baseline", "alternative")],
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv("APSIM_FIELD_DATASETS_DIR", str(root.parent))
    monkeypatch.setenv("APSIM_FIELD_MODELS_BIN", sys.executable)
    monkeypatch.setenv("APSIM_FIELD_RUNTIME_VERIFIED", "1")
    return root


def test_verified_field_bundle_can_satisfy_gate(tmp_path, monkeypatch):
    root = _catalog(tmp_path, monkeypatch)
    app, store, workflow_id = _workflow(tmp_path, class_id=3, score=0.9)
    store.update_yield_inputs(workflow_id, owner_id="anonymous", inputs=YieldAgronomicInputs(
        field_dataset_id="field-1", confirmed_crop_class_id=3,
        cultivar="cultivar-1", sowing_date=date(2026, 5, 1)))
    workflow = store.get(workflow_id, owner_id="anonymous")
    dataset = load_field_dataset(workflow)
    assert dataset["weather_period"] == ["2026-05-01", "2026-10-30"]
    assessment = assess_yield_inputs(workflow)
    assert assessment.status == "ready"
    assert assessment.field_dataset["source_sha256"]["weather"] == dataset["sources"]["weather"]["sha256"]
    (root / "weather.met").write_text("tampered", encoding="utf-8")
    with pytest.raises(FieldDatasetError, match="校验失败"):
        load_field_dataset(workflow)
    store.close()


def test_remote_weather_location_is_rejected(tmp_path, monkeypatch):
    root = _catalog(tmp_path, monkeypatch)
    app, store, workflow_id = _workflow(tmp_path, class_id=3)
    store.update_yield_inputs(workflow_id, owner_id="anonymous", inputs=YieldAgronomicInputs(
        field_dataset_id="field-1", confirmed_crop_class_id=3,
        cultivar="cultivar-1", sowing_date=date(2026, 5, 1)))
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["field_center_lonlat"] = [118.53, 37.94]
    (root / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(FieldDatasetError, match="位置不匹配"):
        load_field_dataset(store.get(workflow_id, owner_id="anonymous"))
    store.close()


def test_daily_lai_constrains_only_matching_scenarios(tmp_path):
    path = tmp_path / "baseline.Report.csv"
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["Clock.Today", "Wheat.LAI", "Yield"])
        writer.writeheader()
        writer.writerow({"Clock.Today": "2026-09-29", "Wheat.LAI": "2.0", "Yield": "0"})
        writer.writerow({"Clock.Today": "2026-09-30", "Wheat.LAI": "2.4", "Yield": "5000"})
    parsed = _read_daily_report(tmp_path, "baseline", "wheat", date(2026, 9, 30))
    assert parsed["yield_t_ha"] == 5.0
    assert parsed["simulated_lai"] == 2.4
    scenarios = [{"scenario_id": "baseline", "yield_t_ha": 5.0, "simulated_lai": 2.4},
                 {"scenario_id": "alternative", "yield_t_ha": 6.0, "simulated_lai": 4.0}]
    result = _constrain_scenarios(scenarios, observed_lai=2.5)
    assert result["baseline_yield_t_ha"] == result["constrained_yield_t_ha"] == 5.0
    assert result["accepted_scenario_ids"] == ["baseline"]
    with pytest.raises(ApsimFieldError, match="不能给出受约束产量"):
        _constrain_scenarios(scenarios, observed_lai=0.1)
    with path.open("a", newline="") as stream:
        csv.writer(stream).writerow(["2026-09-30", "2.6", "5000"])
    with pytest.raises(ApsimFieldError, match="重复日期"):
        _read_daily_report(tmp_path, "baseline", "wheat", date(2026, 9, 30))


def test_ready_workflow_records_real_runner_result_and_artifact(tmp_path, monkeypatch):
    import runtime.analysis_workflow_runner as workflow_runner

    app, store, workflow_id = _workflow(tmp_path, class_id=3, score=0.9)
    store.update_step(workflow_id, "imagery", owner_id="anonymous", status="completed")
    report = tmp_path / "report.html"
    report.write_text("<html>APSIM</html>")
    monkeypatch.setattr(workflow_runner, "assess_yield_inputs",
                        lambda _workflow: YieldInputAssessment(status="ready", issues=[]))
    monkeypatch.setattr(workflow_runner, "run_field_yield",
                        lambda _workflow, _output: {"baseline_yield_t_ha": 4.0,
                                                   "constrained_yield_t_ha": 4.2,
                                                   "report_path": str(report)})

    class Artifacts:
        registered = []

        def register(self, workflow_id, artifact):
            self.registered.append(artifact.artifact_type)
            if artifact.artifact_type == "apsim_report":
                assert artifact.uri.endswith(".html")
                assert "workflows" in artifact.uri
                return "art-apsim"
            assert artifact.artifact_type in {"workflow_summary_report", "analysis_result_json"}
            return f"art-{artifact.artifact_type}"

    _finish(store, workflow_id, "anonymous", artifact_root=tmp_path, artifacts=Artifacts())
    finished = store.get(workflow_id, owner_id="anonymous")
    step = next(step for step in finished.steps if step.step_id == "yield")
    assert finished.status == "completed"
    assert step.status == "completed"
    assert step.result["constrained_yield_t_ha"] == 4.2
    assert step.result["report_artifact_id"] == "art-apsim"
    store.close()
