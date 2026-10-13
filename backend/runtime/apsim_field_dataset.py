"""Server-owned field datasets for APSIM; client IDs never resolve arbitrary paths."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from schemas.analysis_workflow import AnalysisWorkflowSummary


class FieldDatasetError(ValueError):
    pass


def _verified_file(root: Path, entry: dict[str, Any]) -> Path:
    relative = entry.get("path")
    digest = entry.get("sha256")
    if not isinstance(relative, str) or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise FieldDatasetError("数据文件缺少路径或 SHA-256 校验值")
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise FieldDatasetError("数据文件不在已配置的地块目录中")
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise FieldDatasetError(f"数据文件校验失败：{relative}")
    return path


def _weather_info(path: Path) -> tuple[float, float, date, date]:
    latitude = longitude = None
    dates: set[date] = set()
    columns: list[str] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        match = re.match(r"^(latitude|longitude)\s*=\s*(-?\d+(?:\.\d+)?)", stripped, re.I)
        if match:
            if match.group(1).lower() == "latitude":
                latitude = float(match.group(2))
            else:
                longitude = float(match.group(2))
            continue
        if re.match(r"^year\s+day\s+", stripped, re.I):
            columns = [part.lower() for part in stripped.split()]
            required = {"year", "day", "radn", "maxt", "mint", "rain"}
            if not required <= set(columns):
                raise FieldDatasetError("逐日气象缺少辐射、最高/最低温或降水列")
            continue
        parts = stripped.split()
        if columns and len(parts) >= len(columns) and re.fullmatch(r"\d{4}", parts[0]) and parts[1].isdigit():
            try:
                day = date(int(parts[0]), 1, 1) + timedelta(days=int(parts[1]) - 1)
                values = {kind: float(parts[columns.index(kind)]) for kind in ("radn", "maxt", "mint", "rain")}
                if day.year != int(parts[0]) or not all(math.isfinite(value) for value in values.values()):
                    raise ValueError("nonfinite")
                if not (0 <= values["radn"] <= 60 and -80 <= values["mint"] <= values["maxt"] <= 70
                        and 0 <= values["rain"] <= 1000):
                    raise ValueError("out of range")
            except (ValueError, OverflowError) as exc:
                raise FieldDatasetError("逐日气象包含无效日期或数值") from exc
            if day in dates:
                raise FieldDatasetError("逐日气象包含重复日期")
            dates.add(day)
    if latitude is None or longitude is None or not dates:
        raise FieldDatasetError("逐日气象缺少位置或日期记录")
    start, end = min(dates), max(dates)
    if len(dates) != (end - start).days + 1:
        raise FieldDatasetError("逐日气象日期不连续")
    return latitude, longitude, start, end


def _distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    delta_lat, delta_lon = lat2 - lat1, lon2 - lon1
    h = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    return 6371.0 * 2 * math.asin(min(1.0, math.sqrt(h)))


def _aoi_center(workflow: AnalysisWorkflowSummary) -> tuple[float, float]:
    points: list[tuple[float, float]] = []

    def collect(node: Any) -> None:
        if isinstance(node, (list, tuple)) and len(node) >= 2 and all(isinstance(v, (int, float)) for v in node[:2]):
            points.append((float(node[0]), float(node[1])))
        elif isinstance(node, (list, tuple)):
            for child in node:
                collect(child)

    collect(workflow.aoi.geometry.coordinates)
    if not points:
        raise FieldDatasetError("工作流选区缺少坐标")
    return ((min(p[0] for p in points) + max(p[0] for p in points)) / 2,
            (min(p[1] for p in points) + max(p[1] for p in points)) / 2)


def load_field_dataset(workflow: AnalysisWorkflowSummary) -> dict[str, Any]:
    dataset_id = workflow.yield_inputs.field_dataset_id
    root_setting = os.getenv("APSIM_FIELD_DATASETS_DIR")
    if not dataset_id or not root_setting:
        raise FieldDatasetError("尚未选择已核验的地块 APSIM 数据集")
    root = (Path(root_setting) / dataset_id).resolve()
    catalog = Path(root_setting).resolve()
    if not root.is_relative_to(catalog) or not (root / "manifest.json").is_file():
        raise FieldDatasetError("地块 APSIM 数据集不存在")
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FieldDatasetError("地块数据清单无法读取") from exc
    if manifest.get("dataset_id") != dataset_id or manifest.get("status") != "verified" or not manifest.get("verified_by"):
        raise FieldDatasetError("地块数据清单尚未核验")
    if manifest.get("crop_type") not in {"wheat", "maize", "soybean"}:
        raise FieldDatasetError("数据集作物模型不受支持")
    if workflow.yield_inputs.sowing_date is None or not workflow.yield_inputs.cultivar:
        raise FieldDatasetError("缺少品种或播种日期")
    if manifest.get("cultivar") != workflow.yield_inputs.cultivar or manifest.get("sowing_date") != str(workflow.yield_inputs.sowing_date):
        raise FieldDatasetError("品种或播种日期与已核验的管理记录不一致")
    try:
        center = tuple(float(value) for value in manifest["field_center_lonlat"])
        if len(center) != 2 or _distance_km(center, _aoi_center(workflow)) > 2.0:
            raise FieldDatasetError("选区与数据集地块位置不匹配（超过 2 公里）")
        season_end = date.fromisoformat(manifest["season_end"])
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, FieldDatasetError):
            raise
        raise FieldDatasetError("地块位置或收获日期无效") from exc
    sources: dict[str, dict[str, Any]] = {}
    for kind in ("weather", "soil", "management"):
        entry = manifest.get(kind)
        if not isinstance(entry, dict) or not entry.get("source") or entry.get("status") != "verified":
            raise FieldDatasetError(f"{kind} 来源尚未核验")
        sources[kind] = {**entry, "absolute_path": str(_verified_file(root, entry))}
    weather_lat, weather_lon, weather_start, weather_end = _weather_info(Path(sources["weather"]["absolute_path"]))
    if _distance_km(center, (weather_lon, weather_lat)) > 25.0:
        raise FieldDatasetError("气象站距地块超过 25 公里")
    observation = next((step.result.get("observation_at") for step in workflow.steps if step.step_id == "lai"), None)
    if not observation:
        raise FieldDatasetError("LAI 观测日期缺失")
    observed_date = date.fromisoformat(str(observation)[:10])
    if not (weather_start <= workflow.yield_inputs.sowing_date <= observed_date <= season_end <= weather_end):
        raise FieldDatasetError("气象覆盖期、播期、LAI 日期或收获期不匹配")
    scenarios = manifest.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) < 2 or not any(item.get("id") == "baseline" for item in scenarios):
        raise FieldDatasetError("至少需要基线和一个经核验的管理情景")
    seen: set[str] = set()
    verified_scenarios = []
    for entry in scenarios:
        scenario_id = entry.get("id")
        if not isinstance(scenario_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,60}", scenario_id) or scenario_id in seen:
            raise FieldDatasetError("管理情景 ID 无效或重复")
        seen.add(scenario_id)
        verified_scenarios.append({**entry, "absolute_path": str(_verified_file(root, entry))})
    return {**manifest, "root": str(root), "sources": sources,
            "weather_period": [weather_start.isoformat(), weather_end.isoformat()],
            "weather_station_lonlat": [weather_lon, weather_lat],
            "scenarios": verified_scenarios}
