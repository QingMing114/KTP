"""LAI validity measured against the selected AOI, not its bounding rectangle."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import transform_geom


def assess_lai_raster_quality(raster_path: Path, aoi_geometry: dict[str, Any]) -> dict[str, Any]:
    with rasterio.open(raster_path) as source:
        if source.crs is None:
            raise ValueError("LAI 栅格缺少坐标系")
        projected_aoi = transform_geom("EPSG:4326", source.crs, aoi_geometry)
        inside_aoi = geometry_mask(
            [projected_aoi], out_shape=(source.height, source.width),
            transform=source.transform, invert=True, all_touched=False,
        )
        raster = source.read(1, masked=True)
        valid = (inside_aoi & ~np.ma.getmaskarray(raster)
                 & np.isfinite(raster.data) & (raster.data > 0))
        total = int(np.count_nonzero(inside_aoi))
        count = int(np.count_nonzero(valid))
        return {
            "valid_pixel_count": count,
            "total_pixel_count": total,
            "valid_pixel_fraction": round(count / total, 4) if total else 0.0,
            "quality_basis": "aoi_pixels",
            "bounding_pixel_count": int(raster.size),
        }
