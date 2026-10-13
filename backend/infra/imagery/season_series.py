"""Bounded public Sentinel season observations; original five-image picker stays intact."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from runtime.simple_yield import SimpleYieldError


def search_season_items(provider, geometry: dict, start: date, end: date, *, maximum: int = 36) -> list[dict]:
    body = {"collections": [provider._settings.collection], "intersects": geometry,
            "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z", "limit": 100,
            "query": {"eo:cloud_cover": {"lte": 40}},
            "sortby": [{"field": "properties.datetime", "direction": "asc"}]}
    url = provider._settings.search_url
    items = {}
    try:
        for _ in range(6):
            response = httpx.post(url, json=body, timeout=provider._settings.timeout_seconds)
            response.raise_for_status()
            document = response.json()
            for feature in document.get("features", []):
                acquired = str(feature.get("properties", {}).get("datetime", ""))[:10]
                if not acquired or not start.isoformat() <= acquired <= end.isoformat():
                    continue
                if provider._coverage_percent(feature, geometry) < provider._settings.minimum_coverage_percent:
                    continue
                candidate = {"item_id": feature["id"], "date": acquired,
                             "cloud_cover": feature.get("properties", {}).get("eo:cloud_cover", 100)}
                prior = items.get(acquired)
                if prior is None or candidate["cloud_cover"] < prior["cloud_cover"]:
                    items[acquired] = candidate
            following = next((link for link in document.get("links", []) if link.get("rel") == "next"), None)
            if not following:
                break
            if following.get("method", "POST").upper() != "POST" or urlparse(following.get("href", "")).netloc != urlparse(url).netloc:
                raise SimpleYieldError("series_pagination", "时序服务返回了不受支持的分页方式。")
            url, body = following["href"], following.get("body") or body
        else:
            raise SimpleYieldError("series_limit", "候选影像过多，时序检索超过上限；不截断后假装季节完整。")
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise SimpleYieldError("series_unavailable", "历史 Sentinel 影像服务暂不可用，请稍后重试。") from exc
    ordered = sorted(items.values(), key=lambda item: item["date"])
    if len(ordered) <= maximum:
        return ordered
    # Retain temporal endpoints and a low-cloud observation in each time bin.
    buckets = {}
    span = max(1, (end - start).days)
    for item in ordered[1:-1]:
        bucket = min(maximum - 3, int((date.fromisoformat(item["date"]) - start).days * (maximum - 2) / span))
        if bucket not in buckets or item["cloud_cover"] < buckets[bucket]["cloud_cover"]:
            buckets[bucket] = item
    return sorted([ordered[0], *buckets.values(), ordered[-1]], key=lambda item: item["date"])


def read_ndvi_observation(provider, candidate: dict, geometry: dict, cache_dir: Path) -> dict:
    import numpy as np
    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.mask import mask
    from rasterio.warp import Resampling, aligned_target, reproject, transform_geom
    from infra.imagery.aoi_band_reader import resolve_band_asset

    key = hashlib.sha256(json.dumps({"version": 1, "item": candidate["item_id"], "aoi": geometry}, sort_keys=True).encode()).hexdigest()
    path = cache_dir / f"{key}.json"
    if path.is_file():
        try:
            cached = json.loads(path.read_text())
            if cached.get("item_id") == candidate["item_id"]:
                return cached
        except (ValueError, OSError):
            pass
    item = provider.get_item(candidate["item_id"])
    assets = item.get("assets", {})
    if not isinstance(assets.get("SCL"), dict):
        raise SimpleYieldError("cloud_mask_missing", "时序影像缺少选区级云掩膜。")
    arrays = {}
    reference = None
    processing = item.get("properties", {}).get("s2:processing_baseline", "0")
    try:
        processing = float(processing)
    except (TypeError, ValueError):
        processing = 0.0
    offsets = {}
    options = {"GDAL_HTTP_CONNECTTIMEOUT": "15", "GDAL_HTTP_TIMEOUT": "60", "GDAL_HTTP_MAX_RETRY": "1"}
    with rasterio.Env(**options):
        for band in ("B04", "B08", "SCL"):
            asset = assets[band]
            with rasterio.open(resolve_band_asset(assets, band)) as source:
                projected = transform_geom("EPSG:4326", source.crs, geometry)
                raw, raw_transform = mask(source, [projected], crop=True, indexes=1, filled=True, nodata=0)
                if reference is None:
                    transform, width, height = aligned_target(raw_transform, raw.shape[1], raw.shape[0], (20, 20))
                    reference = (transform, source.crs, height, width, projected)
                target_transform, crs, height, width, _ = reference
                grid = np.zeros((height, width), dtype="float32")
                reproject(raw, grid, src_transform=raw_transform, src_crs=source.crs,
                          dst_transform=target_transform, dst_crs=crs,
                          src_nodata=0, dst_nodata=0,
                          resampling=Resampling.nearest if band == "SCL" else Resampling.bilinear)
                if band != "SCL":
                    metadata = (asset.get("raster:bands") or [{}])[0]
                    scale = metadata.get("scale", source.scales[0])
                    offset = metadata.get("offset", source.offsets[0])
                    if scale == 1 and float(np.max(raw)) > 2:
                        scale = 0.0001
                        # Sentinel L2A PB >= 04.00 raw DN uses BOA_ADD_OFFSET.
                        # Explicit STAC offsets take precedence over this fallback.
                        if "offset" not in metadata and offset == 0 and processing >= 4:
                            offset = -0.1
                    offsets[band] = {"scale": float(scale), "offset": float(offset)}
                    valid_raw = grid > 0
                    grid = grid * scale + offset
                    grid[~valid_raw] = np.nan
                arrays[band] = grid
    transform, crs, height, width, projected = reference
    inside = geometry_mask([projected], out_shape=(height, width), transform=transform, invert=True)
    red, nir, scl = arrays["B04"], arrays["B08"], arrays["SCL"]
    valid = inside & np.isin(scl, [4, 5]) & np.isfinite(red) & np.isfinite(nir) & (red > 0) & (nir > 0)
    total = int(np.count_nonzero(inside))
    count = int(np.count_nonzero(valid))
    if count < 16 or not total or count / total < 0.5:
        raise SimpleYieldError("cloud_coverage", "选区清晰有效像元不足，跳过该次观测。")
    ndvi = (nir[valid] - red[valid]) / (nir[valid] + red[valid])
    row = {**candidate, "ndvi": float(np.median(ndvi)), "valid_pixels": count,
           "valid_fraction": round(count / total, 4), "cloud_mask": "SCL vegetation/nonvegetated land",
           "radiometry": offsets}
    cache_dir.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(row))
    temporary.replace(path)
    return row
