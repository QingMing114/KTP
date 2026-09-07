"""PROSAIL LAI inversion → self-contained HTML report tool.

Pipeline (mirrors dev-data/new/test_inversion_v2_final.py):
  1. Load 13-column text LUT  (LAI B2 B3 B4 B5 B6 B7 B8 B8a Cab LIDFa psoil N)
  2. Read 5-band GeoTIFF      (B2 B3 B4 B7 B8, Float32 0-1)
  3. Row-by-row LUT inversion (top-1% mean strategy)
  4. Build 200×170 thumbnails + statistics
  5. Embed JSON data inline in a self-contained HTML report
  6. Save HTML to LAI_REPORT_OUTPUT_DIR (default: ktp/reports/)
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np

from shared.config.paths import get_lai_report_dir
from v2.shared.schemas import ObservationV2, PackArtifactView

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
_HANDLER_DIR   = Path(__file__).resolve()          # .../v2/tools/lai_report_handler.py
_BACKEND_ROOT  = _HANDLER_DIR.parents[2]           # ktp/backend/
_PROJECT_ROOT  = _BACKEND_ROOT.parent              # ktp/
_KTP_PRODUCT   = _PROJECT_ROOT.parent              # ktp_product/

_DEFAULT_LUT_TXT    = _KTP_PRODUCT / "dev-data" / "new" / "LUT_test.txt"
THUMB_W   = 200
THUMB_H   = 170
SCATTER_N = 800
TOP_FRAC  = 0.01
LAI_NODATA = -9999.0
LAI_COLOR_SCALE: tuple[tuple[float, str], ...] = (
    (0.0, "#440154"),
    (1.0, "#3b528b"),
    (2.0, "#21918c"),
    (3.5, "#5ec962"),
    (5.0, "#fde725"),
    (7.0, "#fff7bc"),
)


# ---------------------------------------------------------------------------
# Thumbnail helpers
# ---------------------------------------------------------------------------

def _block_mean_2d(
    arr: np.ndarray,
    out_h: int,
    out_w: int,
    invalid_val: float = 0.0,
) -> np.ndarray:
    h, w = arr.shape
    bh, bw = h / out_h, w / out_w
    out = np.zeros((out_h, out_w), dtype=np.float32)
    for r in range(out_h):
        r0, r1 = int(r * bh), min(h, int((r + 1) * bh))
        for c in range(out_w):
            c0, c1 = int(c * bw), min(w, int((c + 1) * bw))
            block = arr[r0:r1, c0:c1]
            mask  = block > invalid_val
            out[r, c] = float(np.mean(block[mask])) if mask.any() else 0.0
    return out


def _block_nanmean_2d(arr: np.ndarray, out_h: int, out_w: int) -> np.ndarray:
    h, w = arr.shape
    bh, bw = h / out_h, w / out_w
    out = np.zeros((out_h, out_w), dtype=np.float32)
    for r in range(out_h):
        r0, r1 = int(r * bh), min(h, int((r + 1) * bh))
        for c in range(out_w):
            c0, c1 = int(c * bw), min(w, int((c + 1) * bw))
            v = arr[r0:r1, c0:c1]
            v = v[~np.isnan(v)]
            out[r, c] = float(np.mean(v)) if len(v) > 0 else 0.0
    return out


def _stretch(arr: np.ndarray, p_low: float = 2.0, p_high: float = 98.0) -> np.ndarray:
    valid = arr[arr > 0]
    if len(valid) == 0:
        return np.zeros_like(arr)
    lo = np.percentile(valid, p_low)
    hi = np.percentile(valid, p_high)
    return np.clip((arr - lo) / (hi - lo + 1e-9), 0, 1)


def _arr2list(a: np.ndarray, decimals: int = 3) -> list:
    return [[round(float(v), decimals) for v in row] for row in a]


def _hex_rgb(value: str) -> np.ndarray:
    value = value.lstrip("#")
    return np.array([int(value[index:index + 2], 16) for index in (0, 2, 4)], dtype=np.float32)


def _lai_rgba(lai_map: np.ndarray, valid_mask: np.ndarray) -> np.ndarray:
    """Render LAI with a fixed, reproducible color scale and transparent nodata."""
    values = np.array([item[0] for item in LAI_COLOR_SCALE], dtype=np.float32)
    colors = np.stack([_hex_rgb(item[1]) for item in LAI_COLOR_SCALE])
    clipped = np.clip(lai_map.astype(np.float32), values[0], values[-1])
    rgb = np.zeros((*lai_map.shape, 3), dtype=np.float32)

    for index in range(len(values) - 1):
        lower, upper = values[index], values[index + 1]
        mask = (clipped >= lower) & (clipped <= upper if index == len(values) - 2 else clipped < upper)
        ratio = np.clip((clipped[mask] - lower) / max(float(upper - lower), 1e-9), 0.0, 1.0)
        rgb[mask] = colors[index] + ratio[:, None] * (colors[index + 1] - colors[index])

    rgba = np.zeros((*lai_map.shape, 4), dtype=np.uint8)
    rgba[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    rgba[..., 3] = np.where(valid_mask, 210, 0).astype(np.uint8)
    return rgba


# ---------------------------------------------------------------------------
# HTML template builder
# ---------------------------------------------------------------------------

def _build_html(report_data: dict, source_file: str, lut_file: str) -> str:
    """Return a fully self-contained HTML string with report_data inlined."""
    meta = report_data["meta"]
    subtitle = (
        f"{source_file} · LUT: {lut_file} · "
        f"{meta['width']}×{meta['height']} px · 10m 分辨率"
    )
    inline_json = json.dumps(report_data, separators=(",", ":"), ensure_ascii=False)

    configured_template = os.environ.get("LAI_REPORT_TEMPLATE_PATH")
    template_path = (
        Path(configured_template).expanduser().resolve()
        if configured_template
        else _KTP_PRODUCT / "dev-data" / "new" / "lai_report_v3.html"
    )
    if not template_path.is_file():
        raise FileNotFoundError(f"LAI 报告模板不存在: {template_path}")

    html = template_path.read_text(encoding="utf-8")
    html = html.replace(
        "2024年7月 · 甘肃省张掖市玉米田 · Sentinel-2 五波段 · 10m 分辨率 · UTM-47N",
        subtitle,
    )
    old_load = (
        "async function loadData() {\n"
        "  document.getElementById('lo-msg').textContent = '读取 lai_report_data.json …';\n"
        "  // Try fetch from same directory\n"
        "  let data;\n"
        "  try {\n"
        "    const resp = await fetch('lai_report_data.json');\n"
        "    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);\n"
        "    document.getElementById('lo-msg').textContent = '解析数据中…';\n"
        "    data = await resp.json();\n"
        "  } catch(e) {\n"
        "    document.getElementById('lo-msg').textContent = '未找到 lai_report_data.json，使用内置演示数据';\n"
        "    await new Promise(r=>setTimeout(r,1200));\n"
        "    data = buildDemoData();\n"
        "  }\n"
        "  return data;\n"
        "}"
    )
    if old_load not in html:
        raise RuntimeError(f"LAI 报告模板格式不兼容，无法注入反演数据: {template_path}")

    new_load = (
        f"const __INLINE_DATA__ = {inline_json};\n"
        "async function loadData() {\n"
        "  document.getElementById('lo-msg').textContent = '加载反演数据…';\n"
        "  return __INLINE_DATA__;\n"
        "}"
    )
    html = html.replace(old_load, new_load, 1)
    if "<title>LAI 遥感反演分析报告</title>" not in html or "const __INLINE_DATA__ =" not in html:
        raise RuntimeError(f"LAI 报告模板校验失败: {template_path}")
    return html


# ---------------------------------------------------------------------------
# Main tool handler
# ---------------------------------------------------------------------------

def run_lai_html_report(
    *,
    image_path: str,
    lut_path: str | None = None,
    output_dir: str | None = None,
    artifact_output_dir: str | None = None,
    query: str | None = None,
    scene_constraints: "dict | None" = None,
    progress_callback: "Callable[[int, int], None] | None" = None,
    **_unused: object,
) -> tuple[ObservationV2, list[PackArtifactView]]:
    """Run full PROSAIL LAI inversion and generate a self-contained HTML report.

    Args:
        image_path: Absolute path to the 5-band GeoTIFF (B2 B3 B4 B7 B8, Float32 0-1).
        lut_path:   Path to 13-column text LUT. Defaults to dev-data/new/LUT_test.txt.
        output_dir: Directory to write the HTML report. Defaults to ktp/reports/.
        artifact_output_dir: Optional directory for GeoTIFF/PNG products.
        query:      Original user query (unused, kept for handler interface compatibility).
    """
    try:
        import rasterio  # noqa: F401
    except ImportError:
        return (
            ObservationV2(
                source="prosail.lai_html_report",
                status="error",
                summary="缺少依赖 rasterio，请执行 pip install rasterio",
                payload={"error": "missing_rasterio"},
            ),
            [],
        )

    t0 = time.time()

    # ---- Resolve paths ----
    img_path = Path(image_path).expanduser().resolve()
    if not img_path.exists():
        return (
            ObservationV2(
                source="prosail.lai_html_report",
                status="error",
                summary=f"TIF 文件不存在: {image_path}",
                payload={"error": "file_not_found", "path": str(img_path)},
            ),
            [],
        )

    resolved_lut = Path(lut_path).expanduser().resolve() if lut_path else _DEFAULT_LUT_TXT
    if not resolved_lut.exists():
        return (
            ObservationV2(
                source="prosail.lai_html_report",
                status="error",
                summary=f"LUT 文件不存在: {resolved_lut}",
                payload={"error": "lut_not_found", "path": str(resolved_lut)},
            ),
            [],
        )

    out_dir = get_lai_report_dir(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    product_dir = Path(artifact_output_dir).expanduser().resolve() if artifact_output_dir else out_dir
    product_dir.mkdir(parents=True, exist_ok=True)

    try:
        import rasterio

        # ---- Step 1: Load LUT ----
        logger.info("lai_html_report | loading lut | %s", resolved_lut)
        lut_all = np.loadtxt(str(resolved_lut))        # (N, 13)
        lut_lai    = lut_all[:, 0]                     # LAI
        lut_refl   = lut_all[:, [1, 2, 3, 6, 7]]      # B2 B3 B4 B7 B8
        lut_params = lut_all[:, 9:13]                  # Cab LIDFa psoil N

        # ── LUT filtering by scene constraints (Step 2) ──
        lut_mask = _build_lut_mask(lut_lai, lut_params, scene_constraints)
        if lut_mask is not None:
            n_before = len(lut_lai)
            lut_lai    = lut_lai[lut_mask]
            lut_refl   = lut_refl[lut_mask]
            lut_params = lut_params[lut_mask]
            logger.info(
                "LUT filtered by scene constraints: %d → %d rows (%.1f%%)",
                n_before, len(lut_lai), 100.0 * len(lut_lai) / n_before,
            )
            if len(lut_lai) < 10:
                logger.warning("LUT after filtering has < 10 rows, ignoring constraints")
                # Revert to full LUT to avoid degenerate inversion
                lut_all    = np.loadtxt(str(resolved_lut))
                lut_lai    = lut_all[:, 0]
                lut_refl   = lut_all[:, [1, 2, 3, 6, 7]]
                lut_params = lut_all[:, 9:13]

        lut_n = lut_refl.shape[0]
        topk  = max(1, int(round(lut_n * TOP_FRAC)))
        logger.info("lai_html_report | lut loaded | n=%d topk=%d", lut_n, topk)

        band_names = ["B2", "B3", "B4", "B7", "B8"]
        lut_lai_hist, lut_edges = np.histogram(lut_lai, bins=14, range=(0, 8))
        lut_band_mean = {n: float(np.mean(lut_refl[:, i])) for i, n in enumerate(band_names)}
        lut_band_p10  = {n: float(np.percentile(lut_refl[:, i], 10)) for i, n in enumerate(band_names)}
        lut_band_p90  = {n: float(np.percentile(lut_refl[:, i], 90)) for i, n in enumerate(band_names)}

        # ---- Step 2: Load image ----
        logger.info("lai_html_report | loading image | %s", img_path)
        with rasterio.open(str(img_path)) as src:
            img = src.read().astype(np.float32)
            source_profile = src.profile.copy()
            source_bounds = src.bounds
            source_crs = src.crs

        n_bands, h_full, w_full = img.shape
        if n_bands < 5:
            return (
                ObservationV2(
                    source="prosail.lai_html_report",
                    status="error",
                    summary=f"TIF 至少需要 5 个波段（B2/B3/B4/B7/B8），当前 {n_bands} 个",
                    payload={"error": "insufficient_bands", "n_bands": n_bands},
                ),
                [],
            )

        # Normalise to 0-1 if stored as DN (e.g. 0-10000)
        if img.max() > 2.0:
            img = img / 10000.0

        band2, band3, band4, band7, band8 = img[0], img[1], img[2], img[3], img[4]

        # ---- Step 3: LUT inversion (BLAS matrix-multiply version) ----
        #
        # Key identity:  ‖a - b‖² = ‖a‖² + ‖b‖² - 2(a·b)
        #
        # The inner-product term  (chunk @ lut.T)  is computed by BLAS with no
        # (B, N_lut, 5) intermediate array, giving ~10-20× speedup vs broadcasting.
        # Additional gains:
        #   • float32 throughout  →  2× less memory, faster BLAS
        #   • argpartition        →  O(N_lut) top-k vs O(N_lut log N_lut) argsort
        #   • larger batch        →  BLAS amortisation (no huge allocs to fear)
        inversion_batch = max(1, int(os.environ.get("LAI_INVERSION_BATCH", 512)))

        # Pre-cast LUT to float32 and precompute per-entry ‖b‖²
        lut_f32    = lut_refl.astype(np.float32)           # (N_lut, 5)
        lut_sq     = (lut_f32 ** 2).sum(axis=1)            # (N_lut,)
        lut_lai_f  = lut_lai.astype(np.float32)
        lut_par_f  = lut_params.astype(np.float32)
        n_lut      = lut_f32.shape[0]

        logger.info(
            "lai_html_report | starting BLAS inversion | %d×%d px | n_lut=%d | batch=%d",
            h_full, w_full, n_lut, inversion_batch,
        )

        lai_map    = np.zeros((h_full, w_full), dtype=np.float32)
        laistd_map = np.zeros((h_full, w_full), dtype=np.float32)
        mse_map    = np.full((h_full, w_full), np.nan, dtype=np.float32)
        param_maps = np.zeros((h_full, w_full, 4), dtype=np.float32)

        # Flatten image to (H*W, 5) and identify valid (all-positive) pixels
        pixels = np.stack([band2, band3, band4, band7, band8], axis=-1).reshape(-1, 5)
        valid_mask_flat = np.all(pixels > 0, axis=1)
        valid_pixels    = pixels[valid_mask_flat].astype(np.float32)    # (V, 5)

        n_valid  = len(valid_pixels)
        lai_flat = np.zeros(n_valid,      dtype=np.float32)
        std_flat = np.zeros(n_valid,      dtype=np.float32)
        mse_flat = np.full(n_valid, np.nan, dtype=np.float32)
        par_flat = np.zeros((n_valid, 4), dtype=np.float32)

        t1 = time.time()
        if progress_callback is not None:
            progress_callback(0, n_valid)

        for start in range(0, n_valid, inversion_batch):
            end   = min(start + inversion_batch, n_valid)
            chunk = valid_pixels[start:end]                   # (B, 5)

            # ‖a‖²: (B,)  |  a·bᵀ: (B, N_lut) via BLAS sgemm
            chunk_sq = (chunk ** 2).sum(axis=1)               # (B,)
            dot      = chunk @ lut_f32.T                      # (B, N_lut)

            # MSE = (‖a‖² + ‖b‖² - 2 a·b) / n_bands
            mse_b = (chunk_sq[:, None] + lut_sq[None, :] - 2.0 * dot) / 5.0  # (B, N_lut)
            # clip negatives from float32 rounding
            np.clip(mse_b, 0.0, None, out=mse_b)

            # Top-k via argpartition  (O(N_lut), unordered)
            sidx = np.argpartition(mse_b, min(topk - 1, n_lut - 1), axis=1)[:, :topk]  # (B, topk)

            top_l = lut_lai_f[sidx]                           # (B, topk)
            lai_flat[start:end] = top_l.mean(axis=1)
            std_flat[start:end] = top_l.std(axis=1)
            # best-match MSE: minimum across all LUT entries
            mse_flat[start:end] = mse_b.min(axis=1)
            par_flat[start:end] = lut_par_f[sidx].mean(axis=1)

            # Each callback corresponds to a completed numerical inversion batch.
            if progress_callback is not None:
                progress_callback(end, n_valid)

            if end == n_valid or (end // inversion_batch) % 10 == 0:
                elapsed = time.time() - t1
                eta = elapsed / end * (n_valid - end) if end < n_valid else 0
                logger.info("lai_html_report | %d/%d px | %.0fs elapsed | ETA %.0fs",
                            end, n_valid, elapsed, eta)

        # Write results back into 2-D maps
        lai_map.reshape(-1)[valid_mask_flat]       = lai_flat
        laistd_map.reshape(-1)[valid_mask_flat]    = std_flat
        mse_map.reshape(-1)[valid_mask_flat]       = mse_flat
        param_maps.reshape(-1, 4)[valid_mask_flat] = par_flat

        logger.info("lai_html_report | inversion done | %.1fs", time.time() - t1)

        # ---- Step 4: Persist geospatial LAI products ----
        if source_crs is None:
            raise RuntimeError("输入反射率 GeoTIFF 缺少 CRS，无法生成地图产物")
        timestamp = int(t0)
        stem = img_path.stem
        lai_filename = f"lai_{stem}_{timestamp}.tif"
        preview_filename = f"lai_preview_{stem}_{timestamp}.png"
        lai_raster_path = product_dir / lai_filename
        lai_preview_path = product_dir / preview_filename
        valid_geo_mask = valid_mask_flat.reshape(h_full, w_full)
        lai_output = np.where(valid_geo_mask, lai_map, LAI_NODATA).astype(np.float32)
        lai_profile = source_profile.copy()
        lai_profile.update(
            driver="GTiff",
            count=1,
            dtype="float32",
            nodata=LAI_NODATA,
            compress="deflate",
            predictor=3,
        )
        with rasterio.open(lai_raster_path, "w", **lai_profile) as destination:
            destination.write(lai_output, 1)
            destination.set_band_description(1, "LAI")
            destination.update_tags(
                units="m2/m2",
                color_scale=json.dumps(LAI_COLOR_SCALE, ensure_ascii=False),
            )

        from PIL import Image
        preview = Image.fromarray(_lai_rgba(lai_map, valid_geo_mask))
        preview.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        preview.save(lai_preview_path, format="PNG", optimize=True)

        from rasterio.warp import transform_bounds
        bounds_wgs84 = transform_bounds(
            source_crs,
            "EPSG:4326",
            source_bounds.left,
            source_bounds.bottom,
            source_bounds.right,
            source_bounds.top,
            densify_pts=21,
        )
        bounds_wgs84_list = [round(float(value), 8) for value in bounds_wgs84]

        # ---- Step 3-legacy: row-by-row version (kept for reference, not called) ----
        # def _invert_row_by_row():
        #     lai_map    = np.zeros((h_full, w_full), dtype=np.float32)
        #     laistd_map = np.zeros((h_full, w_full), dtype=np.float32)
        #     mse_map    = np.full((h_full, w_full), np.nan, dtype=np.float32)
        #     param_maps = np.zeros((h_full, w_full, 4), dtype=np.float32)
        #     for i in range(h_full):
        #         row = np.stack([band2[i], band3[i], band4[i], band7[i], band8[i]], axis=1)
        #         valid = np.all(row > 0, axis=1)
        #         if valid.any():
        #             vp   = row[valid].astype(np.float64)
        #             diff = vp[:, np.newaxis, :] - lut_refl[np.newaxis, :, :]
        #             mse  = np.mean(diff ** 2, axis=2)
        #             sidx = np.argsort(mse, axis=1)[:, :topk]
        #             top_lai = lut_lai[sidx]
        #             lai_map[i][valid]    = np.mean(top_lai, axis=1)
        #             laistd_map[i][valid] = np.std(top_lai, axis=1)
        #             mse_map[i][valid]    = mse[np.arange(len(vp)), sidx[:, 0]]
        #             param_maps[i][valid] = np.mean(lut_params[sidx], axis=1)
        #         if (i + 1) % 200 == 0:
        #             elapsed = time.time() - t1
        #             eta = elapsed / (i + 1) * (h_full - i - 1)
        #             logger.info("row %d/%d | ETA %.0fs", i + 1, h_full, eta)
        #     return lai_map, laistd_map, mse_map, param_maps

        # ---- Step 5: Thumbnails ----
        th_w, th_h = THUMB_W, THUMB_H
        tb2    = _block_mean_2d(band2,              th_h, th_w)
        tb3    = _block_mean_2d(band3,              th_h, th_w)
        tb4    = _block_mean_2d(band4,              th_h, th_w)
        tb7    = _block_mean_2d(band7,              th_h, th_w)
        tb8    = _block_mean_2d(band8,              th_h, th_w)
        t_lai  = _block_mean_2d(lai_map,            th_h, th_w)
        t_std  = _block_mean_2d(laistd_map,         th_h, th_w)
        t_mse  = _block_nanmean_2d(mse_map,         th_h, th_w)
        t_cab  = _block_mean_2d(param_maps[:, :, 0], th_h, th_w)
        t_lidf = _block_mean_2d(param_maps[:, :, 1], th_h, th_w)
        t_ps   = _block_mean_2d(param_maps[:, :, 2], th_h, th_w)
        t_nl   = _block_mean_2d(param_maps[:, :, 3], th_h, th_w)

        with np.errstate(invalid="ignore", divide="ignore"):
            ndvi_full = (band8 - band4) / (band8 + band4 + 1e-6)
            ndvi_full[band8 + band4 <= 0] = 0.0
        t_ndvi = _block_mean_2d(ndvi_full, th_h, th_w, invalid_val=-999)

        thumb_rgb = (
            np.stack([_stretch(tb8), _stretch(tb4), _stretch(tb3)], axis=2) * 255
        ).astype(np.uint8)

        # ---- Step 6: Statistics ----
        valid_lai = lai_map[lai_map > 0].flatten()
        total_px  = h_full * w_full
        valid_px  = int((lai_map > 0).sum())

        hist_counts, hist_edges = np.histogram(valid_lai, bins=14, range=(0, 7))

        valid_mask = (lai_map > 0) & (np.abs(ndvi_full) < 2)
        valid_yx   = np.argwhere(valid_mask)
        rng = np.random.default_rng(42)
        if len(valid_yx) >= SCATTER_N:
            chosen = valid_yx[rng.choice(len(valid_yx), SCATTER_N, replace=False)]
        else:
            chosen = valid_yx
        scatter_pts = [
            {"x": round(float(ndvi_full[r, c]), 3), "y": round(float(lai_map[r, c]), 2)}
            for r, c in chosen
        ]

        total_px_f = float(total_px)
        scene_pct = {
            "water":  round(int((lai_map < 0.5).sum())  / total_px_f * 100, 1),
            "sparse": round(int(((lai_map >= 0.5) & (lai_map < 1.5)).sum()) / total_px_f * 100, 1),
            "mid":    round(int(((lai_map >= 1.5) & (lai_map < 3.5)).sum()) / total_px_f * 100, 1),
            "dense":  round(int((lai_map >= 3.5).sum()) / total_px_f * 100, 1),
        }

        def _safe_mean(arr: np.ndarray) -> float:
            m = arr[arr > 0]
            return round(float(np.mean(m)), 5) if len(m) > 0 else 0.0

        img_band_mean = {
            "B2": _safe_mean(band2), "B3": _safe_mean(band3),
            "B4": _safe_mean(band4), "B7": _safe_mean(band7), "B8": _safe_mean(band8),
        }

        lai_mean   = round(float(np.nanmean(valid_lai)),   3) if len(valid_lai) > 0 else 0.0
        lai_median = round(float(np.nanmedian(valid_lai)), 3) if len(valid_lai) > 0 else 0.0
        lai_min    = round(float(np.nanmin(valid_lai)),    3) if len(valid_lai) > 0 else 0.0
        lai_max    = round(float(np.nanmax(valid_lai)),    3) if len(valid_lai) > 0 else 0.0

        # ---- Step 7: Assemble report_data ----
        rgb_list = [
            [[int(thumb_rgb[r, c, 0]), int(thumb_rgb[r, c, 1]), int(thumb_rgb[r, c, 2])]
             for c in range(th_w)]
            for r in range(th_h)
        ]

        report_data = {
            "meta": {
                "width": w_full, "height": h_full,
                "thumb_w": th_w, "thumb_h": th_h,
                "lai_min": lai_min, "lai_max": lai_max,
                "lai_mean": lai_mean, "lai_median": lai_median,
                "lai_std": round(float(np.nanstd(valid_lai)), 3) if len(valid_lai) > 0 else 0.0,
                "veg_ratio": round(valid_px / total_px_f * 100, 1),
                "scene_pct": scene_pct,
                "img_band_mean": img_band_mean,
                "source_file": img_path.name,
                "lut_file": resolved_lut.name,
            },
            "thumb_lai": _arr2list(t_lai, 3),
            "thumb_rgb": rgb_list,
            "thumb_std": _arr2list(t_std, 3),
            "hist": {
                "bins":   [round(float(x), 2) for x in hist_edges[:-1]],
                "counts": [int(x) for x in hist_counts],
            },
            "scatter": scatter_pts,
            "lut_stats": {
                "lai_hist_bins":   [round(float(x), 2) for x in lut_edges[:-1]],
                "lai_hist_counts": [int(x) for x in lut_lai_hist],
                "band_mean": lut_band_mean,
                "band_p10":  lut_band_p10,
                "band_p90":  lut_band_p90,
            },
            "pixel_data": {
                "lai":        _arr2list(t_lai,  3),
                "std":        _arr2list(t_std,  3),
                "ndvi":       _arr2list(t_ndvi, 3),
                "b2":         _arr2list(tb2,    4),
                "b3":         _arr2list(tb3,    4),
                "b4":         _arr2list(tb4,    4),
                "b7":         _arr2list(tb7,    4),
                "b8":         _arr2list(tb8,    4),
                "cab":        _arr2list(t_cab,  1),
                "lidfa":      _arr2list(t_lidf, 1),
                "psoil":      _arr2list(t_ps,   3),
                "n_leaf":     _arr2list(t_nl,   2),
                "match_rmse": _arr2list(t_mse,  5),
            },
        }

        # ---- Step 8: Write self-contained HTML ----
        report_filename = f"lai_report_{stem}_{timestamp}.html"
        report_path = out_dir / report_filename

        html_content = _build_html(report_data, img_path.name, resolved_lut.name)
        report_path.write_text(html_content, encoding="utf-8")
        if not report_path.is_file() or report_path.read_text(encoding="utf-8") != html_content:
            raise RuntimeError(f"LAI 报告写入校验失败: {report_path}")

        total_elapsed = time.time() - t0
        logger.info(
            "lai_html_report | complete | elapsed=%.1fs | report=%s",
            total_elapsed, report_path,
        )

        # URI for frontend: starts with "/" so buildArtifactOpenHref maps to /v2/artifacts/open
        artifact_uri = f"/v2/reports/{report_filename}"

        return (
            ObservationV2(
                source="prosail.lai_html_report",
                status="success",
                summary=(
                    f"LAI 反演报告已生成 — mean={lai_mean:.2f} m²/m², "
                    f"植被覆盖={round(valid_px / total_px_f * 100, 1):.1f}%"
                ),
                payload={
                    "lai_mean": lai_mean,
                    "lai_median": lai_median,
                    "lai_min": lai_min,
                    "lai_max": lai_max,
                    "lai_std": round(float(np.nanstd(valid_lai)), 3) if len(valid_lai) > 0 else 0.0,
                    "vegetation_ratio": round(valid_px / total_px_f * 100, 1),
                    "scene_pct": scene_pct,
                    "report_path": str(report_path),
                    "report_uri": artifact_uri,
                    "lai_raster_path": str(lai_raster_path),
                    "lai_preview_path": str(lai_preview_path),
                    "bounds_wgs84": bounds_wgs84_list,
                    "crs": source_crs.to_string(),
                    "nodata": LAI_NODATA,
                    "color_scale": [[value, color] for value, color in LAI_COLOR_SCALE],
                    "elapsed_seconds": round(total_elapsed, 1),
                },
            ),
            [
                PackArtifactView(
                    pack_name="prosail",
                    artifact_type="lai_html_report",
                    title=f"LAI 反演分析报告 — {img_path.name}",
                    content=(
                        f"LAI 均值: {lai_mean:.2f} m²/m²  "
                        f"LAI 中位数: {lai_median:.2f} m²/m²\n"
                        f"值域: {lai_min:.2f} – {lai_max:.2f} m²/m²  "
                        f"植被覆盖: {round(valid_px / total_px_f * 100, 1):.1f}%\n"
                        f"茂密冠层: {scene_pct.get('dense', 0):.1f}%  "
                        f"中等覆盖: {scene_pct.get('mid', 0):.1f}%\n"
                        f"耗时: {total_elapsed:.1f}s"
                    ),
                    uri=artifact_uri,
                ),
                PackArtifactView(
                    pack_name="prosail",
                    artifact_type="lai_raster",
                    title=f"LAI GeoTIFF — {img_path.name}",
                    content=f"单波段 Float32 LAI；CRS={source_crs}; nodata={LAI_NODATA}",
                    uri=str(lai_raster_path),
                ),
                PackArtifactView(
                    pack_name="prosail",
                    artifact_type="lai_preview",
                    title=f"LAI 地图预览 — {img_path.name}",
                    content="固定 0–7 m²/m² 色标；透明区域为 nodata。",
                    uri=str(lai_preview_path),
                ),
            ],
        )

    except Exception as exc:
        logger.exception("lai_html_report | failed | %s", exc)
        return (
            ObservationV2(
                source="prosail.lai_html_report",
                status="error",
                summary=f"LAI 反演报告生成失败: {exc}",
                payload={"error": str(exc)},
            ),
            [],
        )


# ── LUT filtering helper (Step 2) ──


def _build_lut_mask(
    lut_lai: "np.ndarray",
    lut_params: "np.ndarray",   # columns: Cab(0) LIDFa(1) psoil(2) N(3)
    constraints: "dict | None",
) -> "np.ndarray | None":
    """Return boolean mask for LUT rows satisfying scene_constraints.

    Returns None if constraints is empty/None (no filtering needed).
    """
    if not constraints:
        return None

    import numpy as np
    mask = np.ones(len(lut_lai), dtype=bool)

    def _apply(arr, key):
        r = constraints.get(key)
        if r and len(r) == 2:
            mask[:] &= (arr >= r[0]) & (arr <= r[1])

    _apply(lut_lai,          "lai_range")
    _apply(lut_params[:, 0], "cab_range")
    _apply(lut_params[:, 1], "lidfa_range")
    _apply(lut_params[:, 2], "psoil_range")

    return mask if mask.any() else None  # None = filter empty, caller falls back
