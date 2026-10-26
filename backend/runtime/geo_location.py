"""Offline reverse geocoding: AOI centroid -> Chinese province.

The crop judgement must not trust the selected farm preset on its own: a user
can draw an AOI anywhere while a demo farm stays selected. This module resolves
the location from the coordinates with a bundled province boundary asset, so
the agronomic prior always describes the field that was actually analysed.

Asset: Natural Earth 1:50m Admin-1 (public domain), simplified to ~1 km.
Only mainland province-level units are included; Hong Kong, Macao and Taiwan
are intentionally absent and fall back to coordinates-only behaviour.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DATA_PATH = Path(__file__).parent / "data" / "china_admin_provinces.geojson"
# AOIs can straddle a coastline or a simplified border; accept a near-border hit.
_BORDER_TOLERANCE_DEGREES = 0.05
_NEAREST_TOLERANCE_DEGREES = 0.3


@lru_cache(maxsize=1)
def _boundary_index() -> tuple[Any, list[dict[str, Any]]] | None:
    if not DATA_PATH.is_file():
        logger.warning("geo_location_asset_missing | path=%s", DATA_PATH)
        return None
    from shapely.geometry import shape
    from shapely.strtree import STRtree

    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    geometries, properties = [], []
    for feature in payload.get("features", []):
        try:
            geometries.append(shape(feature["geometry"]))
            properties.append(feature.get("properties", {}))
        except Exception:  # pragma: no cover - a broken asset row must not break runs
            logger.warning("geo_location_feature_invalid")
    if not geometries:
        return None
    return STRtree(geometries), properties


def _result(properties: dict[str, Any], *, source: str) -> dict[str, Any]:
    return {
        "province": properties.get("name_zh"),
        "province_en": properties.get("name_en"),
        "iso": properties.get("iso"),
        "source": source,
    }


def reverse_geocode(lat: float | None, lon: float | None) -> dict[str, Any] | None:
    """Return the province containing the point, or the nearest one near a border."""
    if lat is None or lon is None:
        return None
    index = _boundary_index()
    if index is None:
        return None
    from shapely.geometry import Point

    tree, properties = index
    geometries = list(tree.geometries)
    point = Point(float(lon), float(lat))
    for coordinate in (point, point.buffer(_BORDER_TOLERANCE_DEGREES)):
        for position in tree.query(coordinate):
            if geometries[int(position)].covers(point):
                return _result(properties[int(position)], source="admin_boundary")
    nearest = tree.nearest(point)
    if nearest is not None and geometries[int(nearest)].distance(point) <= _NEAREST_TOLERANCE_DEGREES:
        return _result(properties[int(nearest)], source="admin_boundary_nearest")
    return None
