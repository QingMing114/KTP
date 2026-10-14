"""Normalize report display data without rerunning or changing the inversion."""
from __future__ import annotations

from copy import deepcopy
import math


def prepare_report_data(data: dict) -> dict:
    data = deepcopy(data)
    pd, meta = data.get("pixel_data"), data["meta"]
    if not pd:
        return data
    old_w, old_h = meta["thumb_w"], meta["thumb_h"]
    width, height = min(old_w, meta["width"]), min(old_h, meta["height"])
    # Legacy upsampling left empty blocks. Each source cell's data is in the
    # last display cell before its next source boundary; recover those cells.
    xs = [math.ceil((x + 1) * old_w / width) - 1 for x in range(width)]
    ys = [math.ceil((y + 1) * old_h / height) - 1 for y in range(height)]
    def sample(arr):
        return [[arr[y][x] for x in xs] for y in ys]
    for key, arr in pd.items():
        pd[key] = sample(arr)
    for key in ("thumb_rgb", "thumb_lai", "thumb_std"):
        if key in data:
            data[key] = sample(data[key])
    meta.update(thumb_w=width, thumb_h=height, pixel_data_version=2)
    if "match_mse" not in pd:
        pd["match_mse"] = deepcopy(pd["match_rmse"])
        pd["match_rmse"] = [[math.sqrt(v) if v is not None and v >= 0 else None for v in row]
                            for row in pd["match_mse"]]
    if "valid" not in pd:
        pd["valid"] = [[all(isinstance(pd[k][y][x], (int, float)) and math.isfinite(pd[k][y][x])
                              and pd[k][y][x] > 0 for k in ("b2", "b3", "b4", "b7", "b8"))
                        for x in range(width)] for y in range(height)]
    for y in range(height):
        for x in range(width):
            if not pd["valid"][y][x]:
                for key in pd:
                    if key != "valid":
                        pd[key][y][x] = None
                data["thumb_lai"][y][x] = None
                data["thumb_std"][y][x] = None
    if (width, height) == (meta["width"], meta["height"]):
        count = sum(bool(value) for row in pd["valid"] for value in row)
        meta.update(valid_pixel_count=count, nodata_pixel_count=width * height - count)
        if "scene_pct" in meta:
            water = sum(value is not None and value < .5 for row in pd["lai"] for value in row)
            meta["scene_pct"]["water"] = round(water / (width * height) * 100, 1)
    return data
