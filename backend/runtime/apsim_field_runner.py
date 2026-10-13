"""Run verified APSIM field scenarios and constrain them with one dated LAI observation."""

from __future__ import annotations

import csv
import html
import json
import math
import os
import statistics
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

from runtime.apsim_field_dataset import load_field_dataset
from schemas.analysis_workflow import AnalysisWorkflowSummary


class ApsimFieldError(RuntimeError):
    pass


_CROP_NODE = {"wheat": "Wheat", "maize": "Maize", "soybean": "Soybean"}


def _prepare_template(template_path: Path, weather_path: Path, output_path: Path) -> None:
    try:
        document = json.loads(template_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ApsimFieldError("APSIM 地块模板不是有效 JSON") from exc
    weather_count = report_count = 0

    def visit(node: Any) -> None:
        nonlocal weather_count, report_count
        if not isinstance(node, dict):
            return
        if node.get("Name") == "Weather" and "Weather" in node.get("$type", ""):
            node["FileName"] = str(weather_path)
            weather_count += 1
        if "Report" in node.get("$type", "") and isinstance(node.get("VariableNames"), list):
            names = node["VariableNames"]
            if any(".LAI" in name for name in names) and any("Yield" in name or "Grain.Total.Wt" in name for name in names):
                node["EventNames"] = ["[Clock].DoReport"]
                report_count += 1
        for child in node.get("Children", []):
            visit(child)

    visit(document)
    if not weather_count or not report_count:
        raise ApsimFieldError("APSIM 模板缺少气象节点或 LAI/产量日报节点")
    output_path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")


def _read_daily_report(work_dir: Path, stem: str, crop: str, observation_date: date,
                       season_start: date | None = None, season_end: date | None = None) -> dict[str, Any]:
    candidates = sorted(work_dir.glob(f"{stem}.*.csv"))
    crop_node = _CROP_NODE[crop]
    for path in candidates:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            columns = set(reader.fieldnames or [])
            date_column = next((name for name in columns if name.endswith("Clock.Today")), None)
            lai_column = next((name for name in columns if name.endswith(f"{crop_node}.LAI")), None)
            yield_column = "Yield" if "Yield" in columns else next(
                (name for name in columns if name.endswith(f"{crop_node}.Grain.Total.Wt")), None)
            if not date_column or not lai_column or not yield_column:
                continue
            rows = [row for row in reader if
                    (season_start is None or str(row.get(date_column, ""))[:10] >= season_start.isoformat())
                    and (season_end is None or str(row.get(date_column, ""))[:10] <= season_end.isoformat())]
        simulation_ids = {row.get("SimulationID") for row in rows if row.get("SimulationID")}
        if len(simulation_ids) > 1 or len({str(row[date_column])[:10] for row in rows}) != len(rows):
            raise ApsimFieldError("APSIM 日报包含多个模拟或重复日期，不能汇总为单个地块结果")
        observed = next((row for row in rows if str(row[date_column])[:10] == observation_date.isoformat()), None)
        if observed is None:
            raise ApsimFieldError("APSIM 日报没有 LAI 观测日，不能进行同日约束")
        try:
            simulated_lai = float(observed[lai_column])
            yields = [float(row[yield_column]) for row in rows if row.get(yield_column)]
            if not yields or not math.isfinite(simulated_lai) or not all(math.isfinite(value) for value in yields):
                raise ValueError("nonfinite")
        except (ValueError, TypeError) as exc:
            raise ApsimFieldError("APSIM 日报包含无效 LAI 或产量") from exc
        # APSIM Yield is kg/ha; grain dry matter Wt is g/m².
        divisor = 1000.0 if yield_column == "Yield" else 100.0
        return {"simulated_lai": simulated_lai, "yield_t_ha": max(yields) / divisor,
                "daily_report_path": str(path), "report_days": len(rows), "yield_column": yield_column}
    raise ApsimFieldError("APSIM 未生成包含每日 LAI 和产量的 CSV 报表")


def _constrain_scenarios(rows: list[dict[str, Any]], observed_lai: float) -> dict[str, Any]:
    tolerance = max(0.5, 0.25 * observed_lai)
    for row in rows:
        row["lai_residual"] = round(row["simulated_lai"] - observed_lai, 4)
        row["matches_lai"] = abs(row["lai_residual"]) <= tolerance
    accepted = [row for row in rows if row["matches_lai"]]
    baseline = next(row for row in rows if row["scenario_id"] == "baseline")
    if not accepted:
        raise ApsimFieldError("所有 APSIM 情景与观测日 LAI 不符，不能给出受约束产量")
    constrained_yields = [row["yield_t_ha"] for row in accepted]
    return {
        "method": "same_day_simulated_lai_constraint_v1",
        "observed_lai": observed_lai, "lai_tolerance": round(tolerance, 4),
        "baseline_yield_t_ha": round(baseline["yield_t_ha"], 4),
        "baseline_lai_residual": baseline["lai_residual"],
        "constrained_yield_t_ha": round(statistics.median(constrained_yields), 4),
        "constrained_yield_range_t_ha": [round(min(constrained_yields), 4), round(max(constrained_yields), 4)],
        "accepted_scenario_ids": [row["scenario_id"] for row in accepted],
        "scenario_count": len(rows), "accepted_count": len(accepted),
        "scenarios": rows,
        "uncertainty_note": "LAI 容差为探索性规则，产量区间仅反映已提供的管理情景；尚需地面产量验证。",
    }


def run_field_yield(workflow: AnalysisWorkflowSummary, output_dir: Path) -> dict[str, Any]:
    dataset = load_field_dataset(workflow)
    binary = os.getenv("APSIM_FIELD_MODELS_BIN")
    if not binary or os.getenv("APSIM_FIELD_RUNTIME_VERIFIED") != "1" or not Path(binary).is_file():
        raise ApsimFieldError("APSIM 地块运行环境尚未配置或验证")
    output_dir.mkdir(parents=True, exist_ok=True)
    lai_step = next(step for step in workflow.steps if step.step_id == "lai")
    observed_at = str(lai_step.result["observation_at"])
    observed_lai = float(lai_step.result["lai_mean"])
    scenario_results = []
    for scenario in dataset["scenarios"]:
        scenario_id = scenario["id"]
        work_dir = output_dir / scenario_id
        work_dir.mkdir(parents=True, exist_ok=True)
        source = Path(scenario["absolute_path"])
        target = work_dir / f"{scenario_id}.apsimx"
        _prepare_template(source, Path(dataset["sources"]["weather"]["absolute_path"]), target)
        environment = dict(os.environ)
        native_path = os.getenv("APSIM_FIELD_LIBRARY_PATH")
        if native_path:
            environment["LD_LIBRARY_PATH"] = native_path + (":" + environment["LD_LIBRARY_PATH"]
                                                       if environment.get("LD_LIBRARY_PATH") else "")
        try:
            process = subprocess.run([binary, str(target), "--csv"], cwd=work_dir,
                                     capture_output=True, text=True, timeout=300, env=environment)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ApsimFieldError(f"APSIM 情景 {scenario_id} 无法完成运行") from exc
        if process.returncode or "ERRORS FOUND" in process.stdout:
            detail = (process.stderr or process.stdout)[-1500:]
            raise ApsimFieldError(f"APSIM 情景 {scenario_id} 执行失败：{detail}")
        parsed = _read_daily_report(work_dir, scenario_id, dataset["crop_type"],
                                    date.fromisoformat(observed_at[:10]),
                                    season_start=workflow.yield_inputs.sowing_date,
                                    season_end=date.fromisoformat(dataset["season_end"]))
        scenario_results.append({"scenario_id": scenario_id, **parsed})
    constrained = _constrain_scenarios(scenario_results, observed_lai)
    provenance = {
        "dataset_id": dataset["dataset_id"], "verified_by": dataset["verified_by"],
        "crop_type": dataset["crop_type"], "cultivar": dataset["cultivar"],
        "sowing_date": dataset["sowing_date"], "observed_at": observed_at,
        "weather_period": dataset["weather_period"],
        "weather_station_lonlat": dataset["weather_station_lonlat"],
        "source_sha256": {kind: dataset["sources"][kind]["sha256"]
                          for kind in ("weather", "soil", "management")},
        "scenario_sha256": {item["id"]: item["sha256"] for item in dataset["scenarios"]},
    }
    result = {**constrained, "input_provenance": provenance,
              "imagery_item_id": workflow.imagery_item_id,
              "lai_analysis_id": lai_step.analysis_id}
    (output_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    safe = html.escape
    report = ("<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>APSIM 地块情景估产</title>"
              "<body><h1>APSIM 地块情景估产</h1>"
              f"<p>数据集 {safe(dataset['dataset_id'])}；作物 {safe(dataset['crop_type'])}；LAI 观测日 {safe(observed_at[:10])}</p>"
              f"<p>基线产量 {constrained['baseline_yield_t_ha']:.3f} t/ha；LAI 约束后中位数 {constrained['constrained_yield_t_ha']:.3f} t/ha</p>"
              f"<p>情景范围 {constrained['constrained_yield_range_t_ha'][0]:.3f}–{constrained['constrained_yield_range_t_ha'][1]:.3f} t/ha；"
              f"入选 {constrained['accepted_count']}/{constrained['scenario_count']} 个情景。</p>"
              f"<p>LAI 容差 {constrained['lai_tolerance']:.3f}；基线 LAI 残差 {constrained['baseline_lai_residual']:.3f}。</p>"
              f"<p>{safe(constrained['uncertainty_note'])}</p>"
              f"<pre>{safe(json.dumps(provenance, ensure_ascii=False, indent=2))}</pre></body></html>")
    report_path = output_dir / "report.html"
    report_path.write_text(report, encoding="utf-8")
    result["report_path"] = str(report_path)
    return result
