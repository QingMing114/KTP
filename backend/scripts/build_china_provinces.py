"""Build the offline province boundary asset used for AOI reverse geocoding.

Source: Natural Earth 1:50m Admin 1 – States/Provinces (public domain).
Only Chinese province-level features are kept and simplified to keep the
bundled asset small; borders are approximated to roughly a kilometre, which is
sufficient for telling provinces apart (e.g. Shandong vs Gansu).

Usage (network required once, not part of the running service):
    python backend/scripts/build_china_provinces.py
"""

from __future__ import annotations

import json
import urllib.request
from datetime import date
from pathlib import Path

from shapely.geometry import mapping, shape

SOURCE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/"
    "geojson/ne_50m_admin_1_states_provinces.geojson"
)
OUTPUT = Path(__file__).resolve().parents[1] / "runtime" / "data" / "china_admin_provinces.geojson"
SIMPLIFY_DEGREES = 0.01  # ~1.1 km at mid latitudes


def main() -> None:
    with urllib.request.urlopen(urllib.request.Request(SOURCE_URL, headers={"User-Agent": "ktp-build"}), timeout=120) as response:
        collection = json.load(response)
    features = []
    for feature in collection.get("features", []):
        properties = feature.get("properties", {})
        if properties.get("adm0_a3") != "CHN":
            continue
        geometry = shape(feature["geometry"]).simplify(SIMPLIFY_DEGREES, preserve_topology=True)
        if geometry.is_empty:
            continue
        features.append({
            "type": "Feature",
            "properties": {
                "name_zh": properties.get("name_zh") or properties.get("name"),
                "name_en": properties.get("name"),
                "iso": properties.get("iso_3166_2"),
                "type_en": properties.get("type_en"),
            },
            "geometry": mapping(geometry),
        })
    features.sort(key=lambda item: item["properties"].get("iso") or "")
    payload = {
        "type": "FeatureCollection",
        "name": "china_admin_provinces",
        "metadata": {
            "source": SOURCE_URL,
            "license": "Natural Earth, public domain",
            "simplify_degrees": SIMPLIFY_DEGREES,
            "generated_at": date.today().isoformat(),
            "note": "Province-level reverse geocoding only; nearest border accuracy is approximate.",
        },
        "features": features,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "features": len(features), "bytes": OUTPUT.stat().st_size}, ensure_ascii=False))


if __name__ == "__main__":
    main()
