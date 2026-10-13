"""Cached NASA POWER regional radiation; missing public data stays missing."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date
from pathlib import Path
from uuid import uuid4

import httpx

from runtime.simple_yield import SimpleYieldError

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"


def fetch_power_weather(geometry: dict, start: date, end: date, cache_dir: Path) -> tuple[dict, dict]:
    points = []
    def collect(node):
        if isinstance(node, (list, tuple)) and len(node) >= 2 and all(isinstance(value, (int, float)) for value in node[:2]):
            points.append(node[:2])
        elif isinstance(node, (list, tuple)):
            for child in node:
                collect(child)
    collect(geometry.get("coordinates"))
    if not points:
        raise SimpleYieldError("geometry_invalid", "选区没有有效坐标。")
    center_lon = (min(point[0] for point in points) + max(point[0] for point in points)) / 2
    center_lat = (min(point[1] for point in points) + max(point[1] for point in points)) / 2
    # Representative regional point; avoid repeatedly querying the same grid
    # for every tiny adjacent field. This is never described as a field station.
    lon, lat = round(center_lon * 2) / 2, round(center_lat * 2) / 2
    params = {"parameters": "ALLSKY_SFC_SW_DWN,T2M", "community": "AG", "longitude": lon,
              "latitude": lat, "start": start.strftime("%Y%m%d"), "end": end.strftime("%Y%m%d"),
              "format": "JSON", "time-standard": "LST"}
    key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
    path = cache_dir / f"{key}.json"
    document = None
    if path.is_file():
        try:
            document = json.loads(path.read_text())
        except (ValueError, OSError):
            pass  # An interrupted old cache entry can be fetched again.
    if document is None:
        try:
            response = httpx.get(POWER_URL, params=params, timeout=60)
            response.raise_for_status()
            document = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SimpleYieldError("weather_unavailable", "公开逐日辐射服务暂不可用，请稍后重试；不会使用模拟气象代替。") from exc
        # Only complete historical responses are reusable cache entries.
        solar = document.get("properties", {}).get("parameter", {}).get("ALLSKY_SFC_SW_DWN", {})
        if (document.get("parameters", {}).get("ALLSKY_SFC_SW_DWN", {}).get("units") == "MJ/m^2/day"
            and len(solar) == (end - start).days + 1
            and all(isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 60 for value in solar.values())):
            cache_dir.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(f".{uuid4().hex}.tmp")
            temporary.write_text(json.dumps(document))
            temporary.replace(path)
    if document.get("parameters", {}).get("ALLSKY_SFC_SW_DWN", {}).get("units") != "MJ/m^2/day":
        raise SimpleYieldError("weather_units", "辐射数据单位与估产算法不一致。")
    values = document.get("properties", {}).get("parameter", {})
    result = {}
    for day, solar in values.get("ALLSKY_SFC_SW_DWN", {}).items():
        try:
            observed = date.fromisoformat(f"{day[:4]}-{day[4:6]}-{day[6:8]}")
            temperature = values.get("T2M", {}).get(day)
            if not start <= observed <= end or not math.isfinite(solar) or not 0 <= solar <= 60:
                continue
            result[observed.isoformat()] = {"solar_mj_m2": float(solar),
                "temperature_c": float(temperature) if isinstance(temperature, (int, float)) and -80 <= temperature <= 70 else None}
        except (ValueError, TypeError):
            continue
    if not result:
        raise SimpleYieldError("weather_empty", "所选时期没有可用公开辐射数据。")
    provenance = {"provider": "NASA POWER", "url": POWER_URL, "representative_point_lonlat": [lon, lat],
                  "period": [start.isoformat(), end.isoformat()], "units": "MJ/m^2/day",
                  "time_standard": "LST", "source": document.get("header", {}).get("sources"),
                  "response_sha256": hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest(),
                  "spatial_support": "公开区域格点，非地块测站", "received_days": len(result)}
    return result, provenance
