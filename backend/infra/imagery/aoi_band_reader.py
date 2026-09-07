"""Create a 5-band PROSAIL reflectance GeoTIFF from Sentinel COG assets."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any


class AoiBandReadError(RuntimeError):
    pass


_BANDS = ("B02", "B03", "B04", "B07", "B08")
_ASSET_ALIASES = {
    "B02": ("B02", "b02", "B2", "b2", "blue"),
    "B03": ("B03", "b03", "B3", "b3", "green"),
    "B04": ("B04", "b04", "B4", "b4", "red"),
    "B07": ("B07", "b07", "B7", "b7", "rededge3"),
    "B08": ("B08", "b08", "B8", "b8", "nir"),
}
ProgressCallback = Callable[[str, int], None]


def _report_progress(callback: ProgressCallback | None, detail: str, percent: int) -> None:
    if callback is not None:
        callback(detail, max(0, min(100, percent)))


def _band_read_error_message(band: str, exc: Exception) -> str:
    """Convert GDAL/rasterio failures into useful messages without leaking asset URLs."""
    reason = str(exc).lower()
    if "403" in reason or "forbidden" in reason or "accessdenied" in reason:
        return f"读取 Sentinel {band} 波段失败：影像访问链接已过期，请重新搜索影像后重试。"
    if "404" in reason or "not found" in reason or "nosuchkey" in reason:
        return f"读取 Sentinel {band} 波段失败：远程影像文件不存在，请选择其他影像。"
    if any(token in reason for token in ("timed out", "timeout", "connection", "couldn't connect")):
        return f"读取 Sentinel {band} 波段超时：远程影像服务暂时无响应，请稍后重试。"
    return f"读取 Sentinel {band} 波段失败（{type(exc).__name__}），请重试或选择其他影像。"


def resolve_band_asset(assets: dict[str, Any], band: str) -> str:
    """Resolve common STAC asset key variants without accepting arbitrary URLs."""
    for key in _ASSET_ALIASES.get(
        band,
        (band, band.lower(), band.replace("0", ""), band.lower().replace("0", "")),
    ):
        asset = assets.get(key)
        if isinstance(asset, dict) and isinstance(asset.get("href"), str):
            return asset["href"]
    raise AoiBandReadError(f"所选 Sentinel 影像缺少 {band} 波段，请重新搜索或选择其他影像。")


def read_prosail_reflectance_aoi(
    *,
    item: dict[str, Any],
    geometry: dict[str, Any],
    output_path: str | Path,
    target_resolution_m: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> Path:
    """Read AOI pixels and write B02/B03/B04/B07/B08 as float32 0-1.

    The B02 crop supplies the common target grid. Red-edge bands with a
    different native resolution are reprojected into that grid, which keeps
    the existing LAI report handler's five-band input contract intact.
    """
    try:
        import numpy as np
        import rasterio
        from rasterio.mask import mask
        from rasterio.warp import Resampling, aligned_target, reproject, transform_geom
    except ImportError as exc:  # pragma: no cover - deployment dependency
        raise AoiBandReadError("影像读取组件未安装完整，请联系管理员检查 rasterio 和 numpy。") from exc

    assets = item.get("assets") or {}
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    target_data = None
    target_transform = None
    target_crs = None
    profile: dict[str, Any] | None = None
    stacked: list[Any] = []

    _report_progress(progress_callback, "正在解析 Sentinel 影像波段资源", 0)
    gdal_http_options = {
        "GDAL_HTTP_CONNECTTIMEOUT": os.getenv("SENTINEL_COG_CONNECT_TIMEOUT_SECONDS", "15"),
        "GDAL_HTTP_TIMEOUT": os.getenv("SENTINEL_COG_READ_TIMEOUT_SECONDS", "120"),
        "GDAL_HTTP_MAX_RETRY": os.getenv("SENTINEL_COG_MAX_RETRIES", "2"),
        "GDAL_HTTP_RETRY_DELAY": os.getenv("SENTINEL_COG_RETRY_DELAY_SECONDS", "1"),
    }
    with rasterio.Env(**gdal_http_options):
        for index, band in enumerate(_BANDS):
            _report_progress(
                progress_callback,
                f"正在读取 Sentinel {band} 波段（{index + 1}/{len(_BANDS)}）",
                int(index * 80 / len(_BANDS)),
            )
            href = resolve_band_asset(assets, band)
            try:
                with rasterio.open(href) as source:
                    if source.crs is None:
                        raise AoiBandReadError(f"Sentinel {band} 波段缺少坐标系信息，请选择其他影像。")
                    projected_aoi = transform_geom("EPSG:4326", source.crs, geometry, precision=8)
                    cropped, transform = mask(
                        source,
                        [projected_aoi],
                        crop=True,
                        indexes=1,
                        filled=True,
                        nodata=0,
                    )
                    data = cropped.astype("float32")
                    if target_data is None:
                        if target_resolution_m is not None:
                            if target_resolution_m <= 0:
                                raise AoiBandReadError("目标空间分辨率必须大于 0 米。")
                            if source.crs.is_geographic:
                                raise AoiBandReadError("Sentinel 波段使用地理坐标系，无法按米设置目标分辨率。")
                            target_transform, target_width, target_height = aligned_target(
                                transform,
                                data.shape[1],
                                data.shape[0],
                                (target_resolution_m, target_resolution_m),
                            )
                            resampled = np.zeros((target_height, target_width), dtype="float32")
                            reproject(
                                source=data,
                                destination=resampled,
                                src_transform=transform,
                                src_crs=source.crs,
                                dst_transform=target_transform,
                                dst_crs=source.crs,
                                resampling=Resampling.bilinear,
                                src_nodata=0,
                                dst_nodata=0,
                            )
                            data = resampled
                        else:
                            target_transform = transform
                        target_data, target_crs = data, source.crs
                        profile = source.profile.copy()
                        stacked.append(data)
                    else:
                        aligned = np.zeros_like(target_data, dtype="float32")
                        reproject(
                            source=data,
                            destination=aligned,
                            src_transform=transform,
                            src_crs=source.crs,
                            dst_transform=target_transform,
                            dst_crs=target_crs,
                            resampling=Resampling.bilinear,
                            src_nodata=0,
                            dst_nodata=0,
                        )
                        stacked.append(aligned)
            except AoiBandReadError:
                raise
            except Exception as exc:
                raise AoiBandReadError(_band_read_error_message(band, exc)) from exc

            action = "读取完成" if index == 0 else "读取并对齐完成"
            _report_progress(
                progress_callback,
                f"Sentinel {band} 波段{action}（{index + 1}/{len(_BANDS)}）",
                int((index + 1) * 80 / len(_BANDS)),
            )

    if profile is None or target_transform is None or target_crs is None or not stacked:
        raise AoiBandReadError("当前 AOI 未读取到有效的 Sentinel 反射率数据，请调整区域或更换影像。")

    _report_progress(progress_callback, "正在合并并归一化 AOI 反射率波段", 86)
    image = np.stack(stacked).astype("float32")
    if float(image.max()) > 2.0:
        image /= 10000.0
    profile.update(
        driver="GTiff",
        count=len(_BANDS),
        dtype="float32",
        height=image.shape[1],
        width=image.shape[2],
        transform=target_transform,
        crs=target_crs,
        nodata=0,
        compress="deflate",
    )
    _report_progress(progress_callback, "正在写入 AOI 反射率影像", 92)
    with rasterio.open(output, "w", **profile) as destination:
        destination.write(image)
        destination.descriptions = _BANDS
    _report_progress(progress_callback, "AOI 反射率影像准备完成", 100)
    return output
