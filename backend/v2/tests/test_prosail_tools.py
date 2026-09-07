from __future__ import annotations

from pathlib import Path

import numpy as np

from v2.adapters.python_services.ktp_services import KtpExecutionContext
from v2.runtime.executor import _run_ktp_step
from v2.runtime.planner import ChatFirstPlanner
from v2.shared.schemas import ObservationV2, RequestContextV2
from v2.tools.handlers import run_prosail_invert_lai
from v2.tools.lai_report_handler import run_lai_html_report
from v2.tools.registry import ToolRegistryV2


def test_prosail_invert_lai_accepts_image_path_alias(tmp_path: Path) -> None:
    missing_tif = tmp_path / "demo_lai_input.tif"

    observation, artifacts = run_prosail_invert_lai(
        image_path=str(missing_tif),
        crop_type="wheat",
    )

    assert observation.source == "prosail.invert_lai_tif"
    assert observation.status == "error"
    assert observation.payload["error"] == "file_not_found"
    assert artifacts == []


def test_prosail_invert_lai_ignores_context_fields(tmp_path: Path) -> None:
    missing_tif = tmp_path / "demo_lai_input.tif"

    observation, artifacts = run_prosail_invert_lai(
        image_path=str(missing_tif),
        crop_type="wheat",
        region="henan",
        task_type="crop_health_detection",
    )

    assert observation.source == "prosail.invert_lai_tif"
    assert observation.status == "error"
    assert observation.payload["error"] == "file_not_found"
    assert artifacts == []


def test_prosail_planner_prefers_tif_tool_for_image_paths() -> None:
    visible_tools = {"prosail.invert_lai", "prosail.invert_lai_tif"}
    image_path = "dev-data/new/testimgTIF.tif"
    request_context = RequestContextV2(image_path=image_path)

    preferred = ChatFirstPlanner._infer_preferred_tool_name(
        message=f"请帮我做lai反演，并输出完整的分析报告。输入是 {image_path}",
        request_context=request_context,
        visible_tool_names=visible_tools,
    )

    assert preferred == "prosail.invert_lai_tif"


def test_ktp_lai_macro_forwards_scene_constraints(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_report(**kwargs):
        captured.update(kwargs)
        return (
            ObservationV2(
                source="prosail.lai_html_report",
                status="success",
                summary="ok",
                payload={},
            ),
            [],
        )

    monkeypatch.setattr("v2.tools.lai_report_handler.run_lai_html_report", fake_report)
    context = KtpExecutionContext(
        request_id="req-lai-macro",
        query="生成 LAI 报告",
        region="henan",
        crop_type="wheat",
        task_type="lai_inversion",
        image_path=str(tmp_path / "reflectance.tif"),
        extra_params={"scene_constraints": {"crop_type": "wheat"}},
    )

    observation, artifacts = _run_ktp_step(
        step_name="prosail.lai_html_report",
        context=context,
        tool_registry=ToolRegistryV2(definitions={}),
    )

    assert observation.status == "success"
    assert artifacts == []
    assert captured["scene_constraints"] == {"crop_type": "wheat"}


def test_lai_html_report_emits_real_batch_progress_and_uses_v3_template(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import rasterio
    from rasterio.transform import from_origin

    image_path = tmp_path / "reflectance.tif"
    band_values = [0.08, 0.10, 0.12, 0.18, 0.22]
    image = np.stack(
        [np.full((2, 3), value, dtype=np.float32) for value in band_values],
        axis=0,
    )
    with rasterio.open(
        image_path,
        "w",
        driver="GTiff",
        height=2,
        width=3,
        count=5,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(100.0, 40.0, 0.00002, 0.00002),
    ) as dataset:
        dataset.write(image)

    lut_path = tmp_path / "lut.txt"
    lut = np.zeros((10, 13), dtype=np.float32)
    lut[:, 0] = np.linspace(0.5, 5.0, 10)
    for index, column in enumerate((1, 2, 3, 6, 7)):
        lut[:, column] = np.linspace(band_values[index] * 0.8, band_values[index] * 1.2, 10)
    lut[:, 9] = np.linspace(30, 60, 10)
    lut[:, 10] = 45
    lut[:, 11] = 0.5
    lut[:, 12] = 1.5
    np.savetxt(lut_path, lut)

    progress: list[tuple[int, int]] = []
    monkeypatch.setenv("LAI_INVERSION_BATCH", "2")
    observation, artifacts = run_lai_html_report(
        image_path=str(image_path),
        lut_path=str(lut_path),
        output_dir=str(tmp_path),
        progress_callback=lambda processed, total: progress.append((processed, total)),
    )

    assert observation.status == "success", observation.summary
    assert progress == [(0, 6), (2, 6), (4, 6), (6, 6)]
    report_path = Path(observation.payload["report_path"])
    report_html = report_path.read_text(encoding="utf-8")
    assert report_path.parent == tmp_path.resolve()
    assert "<title>LAI 遥感反演分析报告</title>" in report_html
    assert "const __INLINE_DATA__ =" in report_html
    assert "fetch('lai_report_data.json')" not in report_html
    artifacts_by_type = {artifact.artifact_type: artifact for artifact in artifacts}
    assert artifacts_by_type["lai_html_report"].uri == f"/v2/reports/{report_path.name}"
    assert set(artifacts_by_type) == {"lai_html_report", "lai_raster", "lai_preview"}

    lai_raster_path = Path(observation.payload["lai_raster_path"])
    lai_preview_path = Path(observation.payload["lai_preview_path"])
    assert lai_raster_path.is_file()
    assert lai_preview_path.is_file()
    assert artifacts_by_type["lai_raster"].uri == str(lai_raster_path)
    assert artifacts_by_type["lai_preview"].uri == str(lai_preview_path)
    assert observation.payload["bounds_wgs84"] == [100.0, 39.99996, 100.00006, 40.0]
    assert observation.payload["color_scale"][0][0] == 0.0
    assert observation.payload["color_scale"][-1][0] == 7.0

    with rasterio.open(lai_raster_path) as lai_dataset:
        assert lai_dataset.count == 1
        assert lai_dataset.crs == rasterio.crs.CRS.from_epsg(4326)
        assert lai_dataset.transform == from_origin(100.0, 40.0, 0.00002, 0.00002)
        assert lai_dataset.nodata == -9999.0
        assert np.all(lai_dataset.read(1) > 0)
