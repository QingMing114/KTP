"""Read-only loader for map-workspace demo farms.

The initial demo deliberately uses a project-owned GeoJSON file.  A future
farm-management service can replace this loader without changing the product
API contract.
"""

from __future__ import annotations

import json
from pathlib import Path

from schemas.spatial import FarmResponse, GeoJsonGeometry


class FarmStore:
    def __init__(self, source_path: str | Path | None = None) -> None:
        self._source_path = Path(source_path) if source_path else Path(__file__).parent / "data" / "demo_farms.geojson"
        self._farms = self._load()

    def list_farms(self, *, user_id: str | None = None) -> list[FarmResponse]:
        """Return demo farms. ``user_id`` is reserved for future ownership filtering."""
        del user_id
        return list(self._farms)

    def get_farm(self, farm_id: str) -> FarmResponse | None:
        return next((farm for farm in self._farms if farm.farm_id == farm_id), None)

    def _load(self) -> list[FarmResponse]:
        with self._source_path.open("r", encoding="utf-8") as handle:
            collection = json.load(handle)
        farms: list[FarmResponse] = []
        for feature in collection.get("features", []):
            properties = feature.get("properties", {})
            farms.append(FarmResponse(
                farm_id=properties["farm_id"],
                name=properties["name"],
                location_label=properties["location_label"],
                area_hectares=properties["area_hectares"],
                geometry=GeoJsonGeometry.model_validate(feature["geometry"]),
                is_demo=properties.get("is_demo", True),
                metadata=properties.get("metadata", {}),
            ))
        return farms
