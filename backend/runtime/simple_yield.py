"""Experimental grain dry-matter estimate from an observed season's absorbed PAR.

No fitting to local harvest data, no APSIM, no invented planting dates, and no
extrapolation of a partial season into a final harvest. Bounds are parameter
scenarios, never a confidence interval. See docs/simple_yield_estimation.md.
"""
from __future__ import annotations

import bisect
import math
import statistics
from datetime import date, timedelta
from typing import Any

METHOD = "rue_ndvi_observed_season_v1"
PROFILES = {
    "maize": {"label": "玉米", "rue": 3.3, "rue_bounds": [3.1, 3.51], "hi": 0.50, "hi_bounds": [0.40, 0.55], "max_days": 240},
    "spring_wheat": {"label": "春小麦", "rue": 2.5, "rue_bounds": [2.2, 3.0], "hi": 0.50, "hi_bounds": [0.40, 0.53], "max_days": 240},
    "winter_wheat": {"label": "冬小麦", "rue": 2.5, "rue_bounds": [2.2, 3.0], "hi": 0.50, "hi_bounds": [0.40, 0.53], "max_days": 365},
}
REFERENCES = [
    {"title": "Radiation absorption, growth and yield of cereals", "url": "https://doi.org/10.1017/S0021859600056616"},
    {"title": "Radiation interception and utilization by wheat/maize strip intercropping systems", "url": "https://doi.org/10.1016/j.agrformet.2015.02.004"},
    {"title": "NDVI FPAR representation in LUE models", "url": "https://ris.utwente.nl/ws/portalfiles/portal/476367457/1-s2.0-S0168192324004891-main.pdf"},
    {"title": "NASA POWER Daily API", "url": "https://power.larc.nasa.gov/docs/services/api/temporal/daily/"},
]


class SimpleYieldError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        self.details: dict = {}
        super().__init__(message)


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _observations(values: list[dict], as_of: date) -> list[dict]:
    by_date: dict[date, list[dict]] = {}
    for row in values:
        try:
            day = date.fromisoformat(str(row["date"])[:10])
        except (ValueError, KeyError, TypeError):
            continue
        if day > as_of or not _finite(row.get("ndvi")) or not -1 <= row["ndvi"] <= 1:
            continue
        if not _finite(row.get("valid_fraction")) or row["valid_fraction"] < 0.5 or row.get("valid_pixels", 0) < 16:
            continue
        by_date.setdefault(day, []).append(row)
    rows = [{**max(items, key=lambda item: item["valid_fraction"]), "day": day} for day, items in sorted(by_date.items())]
    if len(rows) < 8:
        raise SimpleYieldError("insufficient_observations", "至少需要 8 个通过选区云掩膜检查的观测日期，单景影像不能估算完整生长季产量。")
    # Do not smooth across a temporal gap. Remove isolated NDVI spikes only.
    for i in range(1, len(rows) - 1):
        if (rows[i + 1]["day"] - rows[i - 1]["day"]).days <= 45:
            values = [rows[j]["ndvi"] for j in (i - 1, i, i + 1)]
            rows[i]["smoothed_ndvi"] = statistics.median(values)
    for row in rows:
        row.setdefault("smoothed_ndvi", row["ndvi"])
    return rows


def _interpolate(rows: list[dict], day: date) -> tuple[float, int]:
    days = [row["day"] for row in rows]
    right = bisect.bisect_left(days, day)
    if right < len(days) and days[right] == day:
        return rows[right]["smoothed_ndvi"], 0
    if right == 0 or right == len(days):
        raise SimpleYieldError("unbracketed_season", "生长周期缺少前后观测，不能外推播种或收获日期。")
    left = right - 1
    gap = (days[right] - days[left]).days
    fraction = (day - days[left]).days / gap
    return rows[left]["smoothed_ndvi"] * (1 - fraction) + rows[right]["smoothed_ndvi"] * fraction, gap


def estimate_observed_season(values: list[dict], weather: dict[str, dict], *, crop: str,
                             as_of: str, area_hectares: float) -> dict:
    if crop not in PROFILES:
        raise SimpleYieldError("crop_unsupported", "自动简化估产首期仅支持玉米、春小麦和冬小麦。")
    if not _finite(area_hectares) or area_hectares <= 0:
        raise SimpleYieldError("area_invalid", "选区面积无效。")
    end = date.fromisoformat(as_of[:10])
    rows = _observations(values, end)
    baseline = sorted(row["smoothed_ndvi"] for row in rows)[max(0, int(len(rows) * 0.1) - 1)]
    peak = max(row["smoothed_ndvi"] for row in rows)
    if peak < 0.45 or peak - baseline < 0.25:
        raise SimpleYieldError("weak_season_signal", "没有识别出清晰的小麦或玉米生长周期；可能为裸地、弱植被或观测不足。")
    threshold = min(0.40, max(0.20, baseline + 0.20 * (peak - baseline)))
    daily = {}
    for offset in range((rows[-1]["day"] - rows[0]["day"]).days + 1):
        day = rows[0]["day"] + timedelta(days=offset)
        daily[day] = _interpolate(rows, day)
    periods: list[tuple[date, date]] = []
    start = None
    for day, (ndvi, _) in daily.items():
        if ndvi >= threshold and start is None:
            start = day
        elif ndvi < threshold and start is not None:
            periods.append((start, day - timedelta(days=1)))
            start = None
    if start is not None and (rows[-1]["day"] - start).days >= 20:
        raise SimpleYieldError("season_in_progress", "当前观测仍处于生长阶段，尚未看到季末下降；不将未结束季节外推成最终收获产量。")
    if crop == "winter_wheat":
        merged = []
        for period in periods:
            if merged:
                previous = merged[-1]
                gap_days = [previous[1] + timedelta(days=i) for i in range(1, (period[0] - previous[1]).days)]
                temperatures = [weather.get(day.isoformat(), {}).get("temperature_c") for day in gap_days]
                if (0 < len(gap_days) <= 120 and previous[1].month in {10, 11, 12, 1, 2}
                    and temperatures and all(_finite(t) for t in temperatures)
                    and statistics.mean(temperatures) < 8):
                    merged[-1] = (previous[0], period[1])
                    continue
            merged.append(period)
        periods = merged
    candidates = []
    for start, finish in periods:
        observed = [row for row in rows if start <= row["day"] <= finish]
        length = (finish - start).days + 1
        if crop == "winter_wheat" and not (start.month in {8, 9, 10, 11} and finish.month in {4, 5, 6, 7, 8} and length >= 150):
            continue
        if (60 <= length <= PROFILES[crop]["max_days"] and len(observed) >= 5
            and max(row["smoothed_ndvi"] for row in observed) >= 0.45
            and rows[0]["day"] < start and rows[-1]["day"] > finish
            and (end - finish).days <= 365):
            candidates.append((start, finish, observed))
    if not candidates:
        raise SimpleYieldError("season_not_identified", "最近一年未识别到前后都有观测的完整生长周期；无法自动确定本次估产范围。")
    start, finish, observed = candidates[-1]
    days = [start + timedelta(days=i) for i in range((finish - start).days + 1)]
    max_gap = max(daily[day][1] for day in days)
    if any(gap > 45 and ndvi >= threshold for day in days for ndvi, gap in [daily[day]]):
        raise SimpleYieldError("observation_gap", "活跃生长期存在超过 45 天的观测空缺，不做长时间遥感外推。")
    absorbed_par = 0.0
    for day in days:
        row = weather.get(day.isoformat(), {})
        solar = row.get("solar_mj_m2")
        if not _finite(solar) or not 0 <= solar <= 60:
            raise SimpleYieldError("weather_incomplete", "识别出的生长期缺少有效逐日辐射数据，不能生成估产数值。")
        # Published generic NDVI/FPAR relation, not local crop calibration.
        fpar = max(0.0, min(0.95, 1.24 * daily[day][0] - 0.168))
        absorbed_par += solar * 0.48 * fpar
    profile = PROFILES[crop]
    # g dry matter / m² -> t / ha uses 0.01, not 0.1 or 10.
    estimate = absorbed_par * profile["rue"] * profile["hi"] * 0.01
    bounds = [absorbed_par * rue * hi * 0.01 for rue, hi in zip(profile["rue_bounds"], profile["hi_bounds"])]
    return {
        "method": METHOD, "experimental": True, "locally_calibrated": False,
        "crop_type": crop, "crop_label": profile["label"],
        "yield_basis": "grain_dry_matter", "estimated_yield_t_ha": round(estimate, 3),
        "parameter_scenario_range_t_ha": [round(value, 3) for value in bounds],
        "range_type": "parameter_scenarios_not_confidence_interval",
        "season": {"start": start.isoformat(), "end": finish.isoformat(), "days": len(days),
                   "source": "automatically_detected_optical_growth_period", "observations": len(observed),
                   "max_observation_gap_days": max_gap, "ndvi_threshold": round(threshold, 4)},
        "as_of": end.isoformat(), "area_hectares": area_hectares,
        "absorbed_par_mj_m2": round(absorbed_par, 3),
        "parameters": {"rue_g_dm_per_mj_apar": profile["rue"], "rue_bounds": profile["rue_bounds"],
                       "harvest_index": profile["hi"], "harvest_index_bounds": profile["hi_bounds"],
                       "par_fraction": 0.48, "fpar_relation": "clip(1.24*NDVI-0.168,0,0.95)",
                       "source": "literature_informed_experimental_scenarios_not_local_calibration"},
        "observations": [{key: value for key, value in row.items() if key != "day"} for row in rows],
        "references": REFERENCES,
        "uncertainty_note": "未用本地实收产量验证。日期为遥感有效生长期，不等于实际播种/收获日期；假设同一地块本季种植所选粮食作物。结果为粮食干重的试验估计，未显式模拟水分、养分胁迫和收获损失；参数情景范围不是置信区间，不保证实际产量落在其中。",
    }
