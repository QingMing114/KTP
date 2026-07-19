from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.canonical.router import _lai_pixel_progress, build_canonical_router
from runtime.artifact_store import ArtifactStore
from shared.config.paths import get_lai_report_dir


def test_lai_report_directory_uses_one_configured_location(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("V2_REPORTS_DIR", str(tmp_path / "legacy"))
    monkeypatch.setenv("LAI_REPORT_OUTPUT_DIR", str(tmp_path / "reports"))

    assert get_lai_report_dir() == (tmp_path / "reports").resolve()
    assert get_lai_report_dir(tmp_path / "explicit") == (tmp_path / "explicit").resolve()


def test_lai_pixel_progress_exposes_current_and_total_pixels() -> None:
    first_detail, first_data = _lai_pixel_progress(0, 2458)
    next_detail, next_data = _lai_pixel_progress(512, 2458)
    done_detail, done_data = _lai_pixel_progress(2458, 2458)

    assert first_detail == "正在反演第 1 / 2458 个有效像元"
    assert first_data == {"processed_pixels": 0, "current_pixel": 1, "total_pixels": 2458}
    assert next_detail == "已完成 512 / 2458 个有效像元，正在处理第 513 个"
    assert next_data["current_pixel"] == 513
    assert done_detail == "已完成 2458 / 2458 个有效像元，正在汇总结果"
    assert done_data["processed_pixels"] == 2458


def test_canonical_artifact_render_reads_generated_report_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAI_REPORT_OUTPUT_DIR", str(tmp_path))
    report_html = "<!DOCTYPE html><html><title>LAI 遥感反演分析报告</title><body>report</body></html>"
    (tmp_path / "lai_report_demo.html").write_text(report_html, encoding="utf-8")

    store = ArtifactStore(db_path=str(tmp_path / "artifacts.sqlite3"))
    artifact_id = store.register(
        "analysis-demo",
        SimpleNamespace(
            pack_name="prosail",
            artifact_type="lai_html_report",
            title="LAI report",
            uri="/v2/reports/lai_report_demo.html",
            content="summary only",
        ),
    )
    app = FastAPI()
    app.state.product_artifact_store = store
    app.include_router(build_canonical_router(), prefix="/api/product/v1")

    response = TestClient(app).get(f"/api/product/v1/artifacts/{artifact_id}/render")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.text == report_html
    store._db.close()
