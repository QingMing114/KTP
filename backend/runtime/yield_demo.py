"""Deterministic synthetic wheat/maize data for an explicitly requested demo."""
from __future__ import annotations

import hashlib
import json
import math
import time
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

from runtime.workflow_reports import REPORT_VERSION, register_map_report
from v2.tools.apsim_report_handler import render_apsim_timeseries_report

DEMO_NOTE = "模拟数据，仅用于功能演示；未运行 APSIM，未读取地块影像、气象或土壤，不代表实际产量。"
DEMO_VERSION = "synthetic_yield_demo_v1"


def build_yield_demo(crop: str, observed_at: str, area_hectares: float) -> dict:
    if crop not in {"wheat", "maize"}:
        raise ValueError("Only wheat and maize demos are supported")
    year = date.fromisoformat(observed_at[:10]).year - 1
    maize = crop == "maize"
    start = date(year, 5, 10) if maize else date(year, 3, 10)
    end = date(year, 9, 20) if maize else date(year, 7, 20)
    days = (end - start).days + 1
    single_yield, bounds = (9.1, [8.0, 10.2]) if maize else (6.2, [5.4, 7.0])
    peak_lai, peak_biomass = (5.4, 2100.0) if maize else (4.8, 1300.0)
    ts = {key: [] for key in ("dates", "lai", "biomass", "grain_wt", "stage")}
    for day in range(days):
        p = day / (days - 1)
        ts["dates"].append((start + timedelta(days=day)).isoformat())
        ts["lai"].append(round(peak_lai * math.sin(math.pi * p) ** 1.6, 3))
        ts["biomass"].append(round(peak_biomass * (3 * p ** 2 - 2 * p ** 3), 2))
        grain_p = max(0.0, min(1.0, (p - 0.55) / 0.45))
        ts["grain_wt"].append(round(single_yield * 100 * (3 * grain_p ** 2 - 2 * grain_p ** 3), 2))
        ts["stage"].append(min(9, 1 + int(p * 9)))
    return {
        "simulated": True, "data_mode": "demo", "demo_version": DEMO_VERSION,
        "method": DEMO_VERSION, "crop_type": crop, "crop_label": "玉米" if maize else "小麦",
        "crop_class_id": 0 if maize else 3, "yield_basis": "grain_dry_matter",
        "estimated_yield_t_ha": single_yield, "parameter_scenario_range_t_ha": bounds,
        "estimated_total_t": round(single_yield * area_hectares, 2),
        "constrained_yield_t_ha": single_yield, "baseline_yield_t_ha": 9.4 if maize else 6.5,
        "constrained_yield_range_t_ha": bounds, "scenario_count": 12, "accepted_count": 8,
        "experimental": True, "locally_calibrated": False, "apsim_executed": False,
        "season": {"start": start.isoformat(), "end": end.isoformat(), "observations": days, "simulated": True},
        "timeseries": ts, "uncertainty_note": DEMO_NOTE + " 示例范围不是置信区间，日期不是实际播收记录。",
    }


def register_yield_demo_report(artifacts, *, workflow, result: dict, output_dir: Path) -> dict:
    season = result["season"]
    parameters = {"simulated": True, "crop_type": result["crop_type"],
                  "region": "模拟地块", "cultivar": "演示预设品种", "station": "未使用实测气象",
                  "start_year": int(season["start"][:4]), "end_year": int(season["end"][:4]),
                  "season_start": season["start"], "season_end": season["end"],
                  "area_hectares": round(workflow.aoi.area_hectares, 2),
                  "estimated_total_t": result["estimated_total_t"], "workflow_id": workflow.workflow_id,
                  "scenario_range_t_ha": result["parameter_scenario_range_t_ha"],
                  "stage_labels": {1:"出苗",2:"苗期",3:"拔节",4:"抽雄",5:"吐丝",6:"灌浆",7:"乳熟",8:"蜡熟",9:"完熟"} if result["crop_type"] == "maize" else None,
                  "data_source": DEMO_VERSION}
    payload = {"report_version": REPORT_VERSION, "template": "apsim_timeseries",
               "parameters": parameters, "result": {key: value for key, value in result.items() if not key.startswith("report_")}}
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(body.encode()).hexdigest()[:16]
    output_dir.mkdir(parents=True, exist_ok=True)
    references = {}
    for suffix, kind, content in [("html", "apsim_report", render_apsim_timeseries_report(result["timeseries"], parameters)),
                                  ("json", "analysis_result_json", body)]:
        path = output_dir / f"yield_demo_{digest}.{suffix}"
        if not path.exists():
            path.write_text(content, encoding="utf-8")
        artifact_id = artifacts.register(workflow.workflow_id, SimpleNamespace(
            pack_name="remote_sensing", artifact_type=kind, title=f"{result['crop_label']}估产模拟演示 · APSIM 模板",
            uri=str(path), content=None, content_type="text/html; charset=utf-8" if suffix == "html" else "application/json"))
        if suffix == "html":
            references.update(report_artifact_id=artifact_id, report_uri=f"/api/product/v1/artifacts/{artifact_id}/render",
                              report_kind=kind, report_version=REPORT_VERSION)
        else:
            references.update(report_data_artifact_id=artifact_id, report_data_uri=f"/api/product/v1/artifacts/{artifact_id}/content")
    return references


def run_yield_demo(workflow, *, workflows, artifacts, artifact_root: Path, step_delay: float = 0.7) -> None:
    result = build_yield_demo(workflow.demo_crop, workflow.imagery_snapshot.acquired_at, workflow.aoi.area_hectares)
    root = artifact_root / "workflows" / workflow.workflow_id
    for step in workflow.steps:
        if step.status == "completed":
            continue
        for progress, description in [(15, "正在加载预设演示数据"), (65, "正在整理模拟生长曲线与结果")]:
            workflows.update_step(workflow.workflow_id, step.step_id, owner_id=workflow.owner_id,
                                  status="running", progress_percent=progress, detail=description + "（模拟）")
            if step_delay:
                time.sleep(step_delay)
        values = {"simulated": True, "data_mode": "demo", "uncertainty_note": DEMO_NOTE}
        if step.step_id in {"yield", "yield_simple"}:
            values = dict(result)
            values.update(register_yield_demo_report(artifacts, workflow=workflow, result=values, output_dir=root / step.step_id))
        else:
            if step.step_id == "crop":
                values.update(predicted_class={"class_id": result["crop_class_id"], "name_zh": result["crop_label"],
                                               "name": workflow.demo_crop, "source": "demo"}, warnings=[DEMO_NOTE])
            elif step.step_id == "lai":
                values.update(lai_mean=round(max(result["timeseries"]["lai"]), 2), observation_date=result["season"]["start"])
            values.update(register_map_report(artifacts, run_id=workflow.workflow_id, output_dir=root / step.step_id,
                          kind="workflow_demo_step_report", title=f"{step.step_id} · 模拟演示步骤",
                          context={"工作流 ID": workflow.workflow_id, "数据来源": "构造的模拟数据"},
                          sections=[{"title": "演示说明", "rows": [["步骤", step.step_id]], "notes": [DEMO_NOTE]}]))
        workflows.update_step(workflow.workflow_id, step.step_id, owner_id=workflow.owner_id,
                              status="completed", progress_percent=100, detail="模拟演示步骤已完成", result=values)
