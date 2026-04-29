from __future__ import annotations

import json
import os
import random
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

_APSIM_MODELS_BIN = os.environ.get(
    "APSIM_MODELS_BIN",
    str(Path(__file__).resolve().parents[4] / "ApsimX" / "bin" / "Release" / "net8.0" / "linux-x64" / "publish" / "Models"),
)

_APSIM_ROOT = os.environ.get(
    "APSIM_ROOT",
    str(Path(__file__).resolve().parents[4] / "ApsimX"),
)

_CROP_MODEL_MAP: dict[str, str] = {
    "wheat": "Wheat",
    "maize": "Maize",
    "soybean": "Soybean",
    "peanut": "Peanut",
    "chickpea": "Chickpea",
    "sorghum": "Sorghum",
    "canola": "Canola",
    "barley": "Barley",
    "rice": "Rice",
    "cotton": "Cotton",
    "sugarcane": "Sugarcane",
    "mungbean": "Mungbean",
    "cowpea": "Cowpea",
    "fababean": "Fababean",
    "lentil": "Lentil",
    "lupin": "Lupin",
    "oats": "Oat",
    "fieldpea": "FieldPea",
    "sunflower": "Sunflower",
}

_CULTIVAR_MAP: dict[str, str] = {
    "Wheat": "Yitpi",
    "Maize": "B_110",
    "Soybean": "Cook",
    "Rice": "IR64",
    "Barley": "Gairdner",
    "Canola": "Hyola50",
    "Sorghum": "Buster",
    "Chickpea": "Amit",
    "Peanut": "Streeton",
    "Cotton": "Sicot71",
}

_REGION_DEFAULTS: dict[str, dict[str, Any]] = {
    "henan": {"latitude": 34.75, "longitude": 113.65, "station": "Zhengzhou", "tav": 14.5, "amp": 13.0},
    "shandong": {"latitude": 36.65, "longitude": 117.0, "station": "Jinan", "tav": 14.0, "amp": 13.5},
    "heilongjiang": {"latitude": 45.75, "longitude": 126.65, "station": "Harbin", "tav": 4.5, "amp": 16.0},
    "hebei": {"latitude": 38.04, "longitude": 114.51, "station": "Shijiazhuang", "tav": 13.0, "amp": 14.0},
    "jiangsu": {"latitude": 32.06, "longitude": 118.8, "station": "Nanjing", "tav": 16.0, "amp": 12.0},
    "anhui": {"latitude": 31.86, "longitude": 117.28, "station": "Hefei", "tav": 16.0, "amp": 12.0},
    "sichuan": {"latitude": 30.57, "longitude": 104.07, "station": "Chengdu", "tav": 17.0, "amp": 8.0},
    "hubei": {"latitude": 30.59, "longitude": 114.31, "station": "Wuhan", "tav": 17.0, "amp": 12.0},
    "hunan": {"latitude": 28.23, "longitude": 112.94, "station": "Changsha", "tav": 18.0, "amp": 11.0},
    "jilin": {"latitude": 43.88, "longitude": 125.32, "station": "Changchun", "tav": 5.5, "amp": 16.5},
}

_TEMPLATE_APSIMX = os.path.join(_APSIM_ROOT, "Tests", "Validation", "Wheat", "GxExM", "GxExM.apsimx")


def _resolve_crop_model(crop_type: str) -> str:
    key = crop_type.lower().strip()
    if key in _CROP_MODEL_MAP:
        return _CROP_MODEL_MAP[key]
    for k, v in _CROP_MODEL_MAP.items():
        if k in key or key in k:
            return v
    return "Wheat"


def _resolve_region_info(region: str) -> dict[str, Any]:
    key = region.lower().strip()
    if key in _REGION_DEFAULTS:
        return _REGION_DEFAULTS[key]
    for k, v in _REGION_DEFAULTS.items():
        if k in key or key in k:
            return v
    return _REGION_DEFAULTS["henan"]


def _generate_met_file(
    work_dir: Path,
    station_name: str,
    latitude: float,
    longitude: float,
    tav: float,
    amp: float,
    start_year: int,
    end_year: int,
) -> Path:
    met_path = work_dir / "weather.met"
    lines = [
        "[weather.met.weather]",
        f"latitude = {latitude}  (DECIMAL DEGREES)",
        f"longitude = {longitude}  (DECIMAL DEGREES)",
        f"tav = {tav}  (oC)    ! annual average ambient temperature",
        f"amp = {amp}  (oC)    ! annual amplitude in mean monthly temperature",
        "",
        "year  day  maxt  mint  radn   rain",
        "()    ()   (oC)  (oC)  (MJ/m2) (mm)",
    ]
    for year in range(start_year, end_year + 1):
        for doy in range(1, 367):
            if _is_leap_year(year) and doy > 366:
                continue
            if not _is_leap_year(year) and doy > 365:
                continue
            month = _doy_to_month(doy, year)
            sf = _season_factor(latitude, month)
            base_max = tav + amp / 2 * sf + 5
            base_min = tav - amp / 2 * sf - 5
            maxt = round(base_max + random.gauss(0, 3), 1)
            mint = round(base_min + random.gauss(0, 2), 1)
            radn = round(max(2, 12 + 10 * sf + random.gauss(0, 3)), 1)
            rain = round(max(0, random.gauss(2.5, 4)), 1)
            lines.append(f" {year}  {doy}  {maxt}  {mint}  {radn}  {rain}")
    met_path.write_text("\n".join(lines), encoding="utf-8")
    return met_path


def _is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _doy_to_month(doy: int, year: int) -> int:
    days_in_month = [31, 28 + (1 if _is_leap_year(year) else 0), 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    cumulative = 0
    for i, dim in enumerate(days_in_month):
        cumulative += dim
        if doy <= cumulative:
            return i + 1
    return 12


def _season_factor(latitude: float, month: int) -> float:
    if latitude >= 0:
        summer = [6, 7, 8]
        winter = [12, 1, 2]
    else:
        summer = [12, 1, 2]
        winter = [6, 7, 8]
    if month in summer:
        return 1.0
    if month in winter:
        return -1.0
    return 0.0 if month in [3, 4, 5, 9, 10, 11] else 0.0


def _generate_apply_config(
    work_dir: Path,
    met_file_name: str,
    start_date: str,
    end_date: str,
    crop_model: str,
    cultivar: str,
    sowing_doy: int,
) -> Path:
    config_path = work_dir / "apply_config.txt"
    lines = [
        f"[Weather].FileName={met_file_name}",
        f"[Clock].Start={start_date}",
        f"[Clock].End={end_date}",
        f"[SowingRule].Script=",
    ]
    config_path.write_text("\n".join(lines), encoding="utf-8")
    return config_path


def _build_apsimx_from_template(
    work_dir: Path,
    crop_model: str,
    met_file_path: str,
    start_date: str,
    end_date: str,
    cultivar: str,
    sowing_doy: int = 288,
) -> Path:
    template_path = Path(_TEMPLATE_APSIMX)
    if not template_path.exists():
        return _build_minimal_apsimx(work_dir, crop_model, met_file_path, start_date, end_date, cultivar, sowing_doy)

    with open(template_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    _modify_apsimx_json(data, met_file_path, start_date, end_date, cultivar, sowing_doy)

    output_path = work_dir / "simulation.apsimx"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return output_path


def _modify_apsimx_json(
    data: dict,
    met_file_path: str,
    start_date: str,
    end_date: str,
    cultivar: str,
    sowing_doy: int,
) -> None:
    def _walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        type_name = node.get("$type", "")
        name = node.get("Name", "")

        if "Weather" in type_name or name == "Weather":
            node["FileName"] = met_file_path

        if "Clock" in type_name or name == "Clock":
            if "StartDate" in node:
                node["StartDate"] = start_date
            if "EndDate" in node:
                node["EndDate"] = end_date
            if "Start" in node:
                node["Start"] = start_date
            if "End" in node:
                node["End"] = end_date

        if "Manager" in type_name or "AgManagers" in type_name:
            code = node.get("Code", "")
            if "Sow" in code or "sow" in code or "SowingRule" in name:
                node["Code"] = _generate_sowing_script(cultivar, sowing_doy)

        children = node.get("Children", [])
        filtered = []
        for child in children:
            child_type = child.get("$type", "")
            child_name = child.get("Name", "")
            if "PredictedObserved" in child_type:
                continue
            if "ExcelInput" in child_type or "ExcelMultiInput" in child_type:
                continue
            if "Tests" in child_type and "Folder" in child_type:
                continue
            if child_name in ("PredictedObserved", "Observed", "Tests", "NDVI", "ExcelInput"):
                continue
            filtered.append(child)
        if filtered or children:
            node["Children"] = filtered

        for child in node.get("Children", []):
            _walk(child)

    _walk(data)


def _generate_sowing_script(cultivar: str, sowing_doy: int) -> str:
    return f"""using Models.Core;
using Models.PMF;
using System;

public class SowingRule : Model
{{
    [Link] Plant Wheat;
    [Link] Clock Clock;

    public override void OnDoDailyInitialisation(object sender, EventArgs e)
    {{
        if (Clock.Today.DayOfYear == {sowing_doy} && Wheat.PlantStatus == "out")
        {{
            Wheat.Sow(cultivar: "{cultivar}", rowSpacing: 250, population: 120, budNumber: 1, rowConfig: "1");
        }}
    }}
}}"""


def _build_minimal_apsimx(
    work_dir: Path,
    crop_model: str,
    met_file_path: str,
    start_date: str,
    end_date: str,
    cultivar: str,
    sowing_doy: int = 288,
) -> Path:
    config = {
        "$type": "Models.Core.Simulations, Models",
        "Version": 1,
        "Name": "Simulations",
        "Children": [
            {
                "$type": "Models.Core.Folder, Models",
                "Name": "KTPSimulation",
                "Children": [
                    {
                        "$type": "Models.Core.Simulation, Models",
                        "Name": "KTPSim",
                        "Children": [
                            {
                                "$type": "Models.Clock, Models",
                                "Name": "Clock",
                                "StartDate": start_date,
                                "EndDate": end_date,
                            },
                            {
                                "$type": "Models.Climate.Weather, Models",
                                "Name": "Weather",
                                "FileName": met_file_path,
                            },
                            {
                                "$type": "Models.Soils.Soil, Models",
                                "Name": "Soil",
                                "Children": [
                                    {
                                        "$type": "Models.Soils.Physical, Models",
                                        "Name": "Physical",
                                        "Thickness": [150, 150, 150, 150, 150],
                                        "BD": [1.2, 1.25, 1.3, 1.35, 1.4],
                                        "AirDry": [0.06, 0.06, 0.06, 0.06, 0.06],
                                        "LL15": [0.12, 0.13, 0.14, 0.15, 0.16],
                                        "DUL": [0.28, 0.3, 0.32, 0.34, 0.35],
                                        "SAT": [0.45, 0.44, 0.43, 0.42, 0.41],
                                    },
                                    {
                                        "$type": "Models.Soils.Water, Models",
                                        "Name": "Water",
                                        "InitialValues": [0.25, 0.28, 0.3, 0.32, 0.33],
                                    },
                                    {
                                        "$type": "Models.Soils.Organic, Models",
                                        "Name": "Organic",
                                        "Carbon": [1.5, 1.2, 0.8, 0.5, 0.3],
                                        "CNRatio": [12, 11, 10, 9, 8],
                                    },
                                ],
                            },
                            {
                                "$type": "Models.PMF.Plant, Models",
                                "Name": crop_model,
                                "ResourceName": crop_model,
                            },
                            {
                                "$type": "Models.AgManagers.Manager, Models",
                                "Name": "SowingRule",
                                "Code": _generate_sowing_script(cultivar, sowing_doy),
                            },
                            {
                                "$type": "Models.Report, Models",
                                "Name": "DailyReport",
                                "VariableNames": [
                                    "[Clock].Today",
                                    f"[{crop_model}].Phenology.Stage",
                                    f"[{crop_model}].Biomass.Total.Wt",
                                    f"[{crop_model}].Grain.Wt",
                                    f"[{crop_model}].LAI",
                                    "[Soil].Water",
                                ],
                                "EventNames": ["[Clock].DoReport"],
                            },
                        ],
                    },
                    {
                        "$type": "Models.Storage.DataStore, Models",
                        "Name": "DataStore",
                    },
                ],
            }
        ],
        "Enabled": True,
    }

    config_path = work_dir / "simulation.apsimx"
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    return config_path


def _run_apsim_simulation(
    apsimx_path: Path,
    work_dir: Path,
    timeout: int = 300,
) -> tuple[bool, str]:
    models_bin = Path(_APSIM_MODELS_BIN)
    if not models_bin.exists():
        return False, f"APSIM Models 可执行文件不存在: {models_bin}\n请设置环境变量 APSIM_MODELS_BIN 指向正确的路径。"

    apsim_root = Path(_APSIM_ROOT)
    env = {**os.environ, "APSIM": str(apsim_root)}

    try:
        result = subprocess.run(
            [str(models_bin), str(apsimx_path), "--csv"],
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if "ERRORS FOUND" in stdout or result.returncode != 0:
            error_lines = stdout.split("\n")[-15:] if stdout else stderr.split("\n")[-15:]
            return False, "APSIM 模拟错误:\n" + "\n".join(error_lines)

        return True, stdout
    except subprocess.TimeoutExpired:
        return False, f"APSIM 模拟超时（{timeout}秒）"
    except Exception as exc:
        return False, f"APSIM 调用异常: {exc}"


def _parse_apsim_output(work_dir: Path) -> dict[str, Any]:
    results: dict[str, Any] = {"tables": {}}

    db_files = list(work_dir.glob("*.db"))
    if db_files:
        db_path = db_files[0]
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            for table_name in tables:
                if table_name.startswith("_"):
                    continue
                try:
                    cursor.execute(f'SELECT * FROM "{table_name}" LIMIT 200')
                    columns = [desc[0] for desc in cursor.description]
                    rows = cursor.fetchall()
                    if rows:
                        results["tables"][table_name] = {
                            "columns": columns,
                            "row_count": len(rows),
                            "sample": [dict(zip(columns, row)) for row in rows[:10]],
                        }
                except Exception:
                    pass
            conn.close()
        except Exception as exc:
            results["db_error"] = str(exc)

    csv_files = list(work_dir.glob("*.csv"))
    if csv_files and not results["tables"]:
        for csv_path in csv_files[:3]:
            try:
                content = csv_path.read_text(encoding="utf-8")
                lines = content.strip().split("\n")
                if len(lines) > 1:
                    headers = lines[0].split(",")
                    sample_rows = [line.split(",") for line in lines[1:min(11, len(lines))]]
                    results["tables"][csv_path.stem] = {
                        "columns": headers,
                        "row_count": len(lines) - 1,
                        "sample": [dict(zip(headers, row)) for row in sample_rows[:5]],
                    }
            except Exception:
                pass

    return results


def run_apsim_crop_simulation(
    *,
    crop_type: str = "wheat",
    region: str = "henan",
    start_year: int | None = None,
    end_year: int | None = None,
    soil_type: str = "Clay",
    sowing_date: str | None = None,
    cultivar: str | None = None,
    query: str | None = None,
) -> tuple[Any, list[Any]]:
    from v2.shared.schemas import ObservationV2, PackArtifactView

    current_year = datetime.now().year
    if start_year is None:
        start_year = current_year - 1
    if end_year is None:
        end_year = current_year

    crop_model = _resolve_crop_model(crop_type)
    region_info = _resolve_region_info(region)
    latitude = region_info["latitude"]
    longitude = region_info["longitude"]
    station = region_info["station"]
    tav = region_info.get("tav", 14.5)
    amp = region_info.get("amp", 13.0)

    if cultivar is None:
        cultivar = _CULTIVAR_MAP.get(crop_model, "Yitpi")

    sowing_doy = 288
    if sowing_date:
        try:
            parts = sowing_date.split("-")
            month, day = int(parts[1]), int(parts[2])
            days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
            sowing_doy = sum(days_in_month[:month - 1]) + day
        except Exception:
            pass

    work_dir = Path(tempfile.mkdtemp(prefix="apsim_"))
    try:
        met_path = _generate_met_file(
            work_dir, station, latitude, longitude, tav, amp, start_year, end_year
        )

        start_date = f"{start_year}-01-01"
        end_date = f"{end_year}-12-31"

        apsimx_path = _build_apsimx_from_template(
            work_dir,
            crop_model,
            str(met_path),
            start_date,
            end_date,
            cultivar,
            sowing_doy,
        )

        success, output = _run_apsim_simulation(apsimx_path, work_dir)

        if not success:
            return (
                ObservationV2(
                    source="apsim.crop_simulation",
                    status="error",
                    summary=f"APSIM 作物模拟失败: {output[:200]}",
                    payload={"crop_type": crop_type, "region": region, "error": output[:500]},
                ),
                [],
            )

        parsed = _parse_apsim_output(work_dir)

        summary_parts = [
            f"APSIM 作物模拟完成。",
            f"作物: {crop_model} ({crop_type})",
            f"品种: {cultivar}",
            f"区域: {region} ({station}, {latitude}°N, {longitude}°E)",
            f"模拟期: {start_date} ~ {end_date}",
        ]

        artifacts: list[PackArtifactView] = []

        for table_name, table_data in parsed.get("tables", {}).items():
            summary_parts.append(f"输出表 {table_name}: {table_data['row_count']} 行")
            if table_data.get("sample"):
                sample_text = json.dumps(table_data["sample"], indent=2, ensure_ascii=False, default=str)
                artifacts.append(
                    PackArtifactView(
                        pack_name="apsim",
                        artifact_type="simulation_data",
                        title=f"APSIM 输出 - {table_name}",
                        content=sample_text,
                    )
                )

        if not parsed.get("tables"):
            summary_parts.append("（未检测到结构化输出表，可能模拟配置需要调整）")
            artifacts.append(
                PackArtifactView(
                    pack_name="apsim",
                    artifact_type="simulation_log",
                    title="APSIM 运行日志",
                    content=output[:2000],
                )
            )

        return (
            ObservationV2(
                source="apsim.crop_simulation",
                status="success",
                summary="\n".join(summary_parts),
                payload={
                    "crop_type": crop_type,
                    "crop_model": crop_model,
                    "cultivar": cultivar,
                    "region": region,
                    "station": station,
                    "latitude": latitude,
                    "longitude": longitude,
                    "start_year": start_year,
                    "end_year": end_year,
                    "tables": list(parsed.get("tables", {}).keys()),
                },
            ),
            artifacts,
        )
    finally:
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:
            pass
