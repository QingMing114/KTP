"""Execute bundled APSIM examples selected only by completed crop recognition."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import subprocess
from pathlib import Path

from runtime.workflow_reports import register_map_report

EXAMPLES = {0: ("maize", "Maize", "玉米"), 2: ("soybean", "Soybean", "大豆"),
            3: ("wheat", "Wheat", "小麦"), 4: ("wheat", "Wheat", "小麦")}
NOTE = "真实运行 APSIM，使用示例气象、土壤、品种和管理参数；识别结果仅用于选择示例，不代表当前地块实际产量，未使用遥感 LAI 约束。"


class ApsimExampleError(RuntimeError):
    pass


def select_example(workflow):
    step = next((step for step in workflow.steps if step.step_id == "crop"), None)
    if step is None or step.status != "completed":
        raise ApsimExampleError("请先完成农作物识别，再自动选择 APSIM 示例。")
    prediction = step.result.get("predicted_class") or {}
    class_id = prediction.get("class_id")
    if type(class_id) is not int or class_id not in EXAMPLES:
        raise ApsimExampleError("识别作物没有对应的小麦、玉米或大豆示例，无法自动模拟。")
    score = prediction.get("score")
    if not isinstance(score, (int, float)) or not math.isfinite(score) or score < 0.60:
        raise ApsimExampleError("作物识别分数不足 0.60，请更换生长期影像后重新识别。")
    scores = sorted((item["score"] for item in step.result.get("class_scores", [])
                     if isinstance(item, dict) and isinstance(item.get("score"), (int, float))
                     and math.isfinite(item["score"])), reverse=True)
    if len(scores) >= 2 and scores[0] - scores[1] < 0.15:
        raise ApsimExampleError("作物识别前两类分差不足 0.15，请更换生长期影像后重新识别。")
    return EXAMPLES[class_id], prediction


def run_example(workflow, output_dir: Path) -> dict:
    (crop, model, label), prediction = select_example(workflow)
    root = Path(os.environ.get("APSIM_EXAMPLE_ROOT", ""))
    binary = Path(os.environ.get("APSIM_EXAMPLE_MODELS_BIN", ""))
    template = root / "Examples" / f"{model}.apsimx"
    weather = root / "Examples/WeatherFiles/AU_Dalby.met"
    if not binary.is_file() or not template.is_file() or not weather.is_file():
        raise ApsimExampleError("APSIM 示例运行环境或配套文件尚未配置。")
    output_dir.mkdir(parents=True, exist_ok=True)
    document = json.loads(template.read_text(encoding="utf-8-sig"))
    counts = {"weather": 0, "clock": 0, "report": 0}

    def visit(node):
        kind = node.get("$type", "")
        if "Models.Climate.Weather," in kind:
            node["FileName"] = str(weather.resolve())
            counts["weather"] += 1
        if "Models.Clock," in kind:
            node.update(Start="1990-01-01T00:00:00", End="1991-12-31T00:00:00")
            counts["clock"] += 1
        if "Models.Report," in kind:
            node["VariableNames"] = ["[Clock].Today as Date", f"[{model}].LAI as LAI",
                f"[{model}].AboveGround.Wt as Biomass", f"[{model}].Grain.Total.Wt as GrainWt",
                f"[{model}].Phenology.Stage as Stage"]
            node["EventNames"] = ["[Clock].DoReport"]
            counts["report"] += 1
        for child in node.get("Children", []):
            visit(child)

    visit(document)
    if not all(counts.values()):
        raise ApsimExampleError("APSIM 示例缺少气象、时钟或日报节点。")
    target = output_dir / f"{model}.apsimx"
    target.write_text(json.dumps(document), encoding="utf-8")
    # Retries must never reuse output from an earlier invocation.
    for old in output_dir.glob(f"{model}.*"):
        if old.suffix in {".csv", ".db"}:
            old.unlink()
    env = {**os.environ, "APSIM": str(root.resolve())}
    scratch = output_dir / "tmp"
    scratch.mkdir(exist_ok=True)
    env["TMPDIR"] = str(scratch.resolve())
    native = os.getenv("APSIM_EXAMPLE_LIBRARY_PATH")
    if native:
        env["LD_LIBRARY_PATH"] = native + ":" + env.get("LD_LIBRARY_PATH", "")
    try:
        process = subprocess.run([str(binary.resolve()), str(target.resolve()), "--csv"],
                                 cwd=output_dir, env=env, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ApsimExampleError("APSIM 示例无法启动或运行超时，请检查运行环境。") from exc
    (output_dir / "simulation.log").write_text(process.stdout + process.stderr, encoding="utf-8")
    if process.returncode or "ERRORS FOUND" in process.stdout:
        raise ApsimExampleError("APSIM 示例运行失败，请检查模拟日志。")
    timeseries = {key: [] for key in ("dates", "lai", "biomass", "grain_wt", "stage")}
    for path in sorted(output_dir.glob(f"{model}.*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not {"Date", "LAI", "Biomass", "GrainWt", "Stage"} <= set(reader.fieldnames or []):
                continue
            for row in reader:
                timeseries["dates"].append(row["Date"][:10])
                for key, column in (("lai", "LAI"), ("biomass", "Biomass"), ("grain_wt", "GrainWt"), ("stage", "Stage")):
                    value = float(row[column])
                    if not math.isfinite(value):
                        raise ApsimExampleError("APSIM 日报含无效数值。")
                    timeseries[key].append(value)
        break
    if not timeseries["dates"] or len(set(timeseries["dates"])) != len(timeseries["dates"]):
        raise ApsimExampleError("APSIM 没有生成有效的单情景生长日报。")
    return {"method": "apsim_example_v1", "apsim_executed": True, "data_mode": "apsim_example",
            "crop_type": crop, "crop_label": label, "crop_prediction": prediction,
            "example_yield_t_ha": max(timeseries["grain_wt"]) / 100,
            "timeseries": timeseries, "season": {"start": "1990-01-01", "end": "1991-12-31"},
            "input_provenance": {"template": template.name, "weather": weather.name,
                "template_sha256": hashlib.sha256(template.read_bytes()).hexdigest(),
                "weather_sha256": hashlib.sha256(weather.read_bytes()).hexdigest(),
                "prepared_template_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "soil_management": "embedded_in_example", "crop_source": "crop_recognition"},
            "uncertainty_note": NOTE}


def register_example_report(artifacts, *, workflow, result, output_dir):
    ts = result["timeseries"]
    provenance = result["input_provenance"]
    return register_map_report(artifacts, run_id=workflow.workflow_id, output_dir=output_dir,
        kind="apsim_report", title=f"{result['crop_label']} APSIM 真实示例模拟",
        context={"模型选择": "农作物识别结果自动匹配", "示例模板": provenance["template"],
                 "配套气象": provenance["weather"], "模拟时段": "1990-01-01 至 1991-12-31"},
        highlights=[{"label": "示例期间最高模拟单产", "value": f"{result['example_yield_t_ha']:.2f}", "unit": "t/ha"}],
        sections=[{"title": "输入来源与用途", "rows": [["作物", result["crop_label"]],
                    ["土壤、品种和管理", "APSIM 示例内置参数"],
                    ["模板 SHA-256", provenance["template_sha256"]], ["气象 SHA-256", provenance["weather_sha256"]]],
                   "notes": [NOTE]}],
        visuals=[{"type": "line", "title": title, "labels": ts["dates"], "values": ts[key]}
                 for title, key in (("模拟 LAI", "lai"), ("模拟生物量 g/m²", "biomass"), ("模拟籽粒干重 g/m²", "grain_wt"))])
