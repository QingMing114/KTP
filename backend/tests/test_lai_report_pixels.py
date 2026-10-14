"""Report grids must retain observations and distinguish nodata from real zeros."""
import json
import re
from copy import deepcopy

import numpy as np
import rasterio
from rasterio.transform import from_origin

from v2.tools.lai_report_data import prepare_report_data
from v2.tools.lai_report_handler import _block_mean_2d, _block_nanmean_2d, run_lai_html_report


def inline_data(html):
    return json.loads(re.search(r"const __INLINE_DATA__ = (.*?);\s*async function loadData", html, re.S).group(1))


def test_small_report_preserves_all_valid_pixels_and_real_zero_values(tmp_path):
    image = np.broadcast_to(np.array([.08, .1, .12, .18, .3])[:, None, None], (5, 3, 4)).copy().astype("float32")
    image[:, 0, 0] = 0
    image[0, 0, 1] = np.nan
    image[0, 0, 2] = np.inf
    path = tmp_path / "reflectance.tif"
    with rasterio.open(path, "w", driver="GTiff", width=4, height=3, count=5, dtype="float32",
                       crs="EPSG:32650", transform=from_origin(611000, 4300000, 20, 20), nodata=0) as dst:
        dst.write(image)
    lut = np.zeros((10, 13))
    lut[:, 0] = 3
    lut[:, [1, 2, 3, 6, 7]] = [.08, .1, .12, .18, .3]
    lut[:, 9:13] = [50, 55, 0, 1.5]
    lut_path = tmp_path / "lut.txt"
    np.savetxt(lut_path, lut)
    observation, _ = run_lai_html_report(image_path=str(path), lut_path=str(lut_path), output_dir=str(tmp_path))
    assert observation.status == "success", observation.summary
    html = (tmp_path / observation.payload["report_path"]).read_text(encoding="utf-8")
    data = inline_data(html)
    assert (data["meta"]["thumb_w"], data["meta"]["thumb_h"]) == (4, 3)
    assert data["meta"]["valid_pixel_count"] == 9
    assert data["meta"]["scene_pct"]["water"] == 0
    assert data["meta"]["resolution"] == [20, 20]
    assert "20 × 20 m 分辨率" in html and "611430" not in html
    pd = data["pixel_data"]
    assert pd["valid"][0] == [False, False, False, True]
    for field in ("lai", "std", "b8", "cab", "psoil", "match_rmse"):
        assert pd[field][0][:3] == [None] * 3
    assert pd["lai"][1] == [3] * 4
    assert pd["b8"][1] == [.3] * 4
    assert pd["std"][1] == [0] * 4
    assert pd["psoil"][1] == [0] * 4
    assert "NaN" not in html and "Infinity" not in html


def test_legacy_padded_report_can_be_repaired_without_recomputing_inversion():
    lai = np.array([[1., 2., 0.], [3., 4., 5.]])
    bands = np.where(lai > 0, .2, 0)
    def padded(arr):
        return _block_mean_2d(arr, 17, 20).tolist()
    report = {
        "meta": {"width": 3, "height": 2, "thumb_w": 20, "thumb_h": 17, "lai_mean": 3},
        "pixel_data": {key: padded(values) for key, values in {
            "lai": lai, "std": np.zeros_like(lai), "ndvi": bands,
            **{b: bands for b in ("b2", "b3", "b4", "b7", "b8")},
            "cab": np.where(lai > 0, 50., 0), "lidfa": np.where(lai > 0, 55., 0),
            "psoil": np.zeros_like(lai), "n_leaf": np.where(lai > 0, 1.5, 0),
            "match_rmse": np.where(lai > 0, .0004, 0),
        }.items()},
        "thumb_rgb": np.zeros((17, 20, 3)).tolist(), "thumb_lai": padded(lai),
        "thumb_std": padded(np.zeros_like(lai)),
    }
    original = deepcopy(report)
    fixed = prepare_report_data(report)
    assert fixed["pixel_data"]["lai"] == [[1, 2, None], [3, 4, 5]]
    assert fixed["pixel_data"]["std"][1] == [0, 0, 0]
    assert abs(fixed["pixel_data"]["match_rmse"][1][0] - .02) < 1e-6
    assert fixed["meta"]["lai_mean"] == original["meta"]["lai_mean"]
    assert prepare_report_data(fixed) == fixed
    assert original == report


def test_downsample_includes_real_zeros_but_excludes_nodata():
    arr = np.array([[0., 1.], [np.nan, 2.]])
    assert _block_nanmean_2d(arr, 1, 1)[0, 0] == 1


def test_refresh_retains_existing_url_and_backs_up_report_and_artifact(tmp_path):
    import sqlite3
    from scripts.refresh_lai_reports import refresh_reports
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    path = report_dir / "lai_report_saved.html"
    values = [[.2, 0]]
    pd = {k: values for k in ("lai", "std", "ndvi", "b2", "b3", "b4", "b7", "b8", "cab", "lidfa", "psoil", "n_leaf", "match_rmse")}
    data = {"meta": {"width": 2, "height": 1, "thumb_w": 2, "thumb_h": 1}, "pixel_data": pd,
            "thumb_lai": values, "thumb_std": values, "thumb_rgb": [[[1, 2, 3], [0, 0, 0]]]}
    html = "const __INLINE_DATA__ = " + json.dumps(data) + ";\nasync function loadData() {}"
    path.write_text(html, encoding="utf-8")
    db_path = tmp_path / "artifacts.db"
    db = sqlite3.connect(db_path)
    db.execute("CREATE TABLE product_artifacts (artifact_id TEXT,payload_json TEXT)")
    record = {"artifact_type": "lai_html_report", "content_path": "/v2/reports/" + path.name, "version": 1}
    db.execute("INSERT INTO product_artifacts VALUES (?,?)", ("existing-artifact", json.dumps(record)))
    db.commit()
    backup = tmp_path / "backup"
    preview = refresh_reports(report_dir, backup, db_path)
    assert len(preview["updated_reports"]) == 1 and path.read_text(encoding="utf-8") == html
    result = refresh_reports(report_dir, backup, db_path, apply=True)
    assert result["artifact_metadata_updated"] == 1
    assert (backup / "reports" / path.name).read_text(encoding="utf-8") == html
    fixed = inline_data(path.read_text(encoding="utf-8"))
    assert fixed["pixel_data"]["lai"] == [[.2, None]]
    saved = json.loads(db.execute("SELECT payload_json FROM product_artifacts WHERE artifact_id='existing-artifact'").fetchone()[0])
    assert saved["content_path"] == record["content_path"] and saved["version"] == 2
    assert refresh_reports(report_dir, backup, db_path, apply=True)["updated_reports"] == []
    db.close()
