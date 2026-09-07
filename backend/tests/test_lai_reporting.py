from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.canonical.router import _lai_pixel_progress, _lai_product_result, build_canonical_router
from infra.imagery.stac_provider import ImagerySearchError
from runtime.artifact_store import ArtifactStore
from runtime.lai_analysis_store import LaiAnalysisStore
from schemas.runtime import ObservationV2, PackArtifactView
from schemas.spatial import AoiGeometry, CreateLaiAnalysisRequest, GeoJsonGeometry, ImageryCandidate
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


def test_lai_product_result_exposes_stable_map_and_download_contract() -> None:
    result = _lai_product_result(
        {
            "bounds_wgs84": [100.0, 39.9, 100.1, 40.0],
            "color_scale": [[0.0, "#440154"], [7.0, "#fff7bc"]],
        },
        report_artifact_id="art_report",
        raster_artifact_id="art_raster",
        preview_artifact_id="art_preview",
    )

    assert result["report_uri"].endswith("/art_report/render")
    assert result["lai_raster_uri"].endswith("/art_raster/content")
    assert result["map_overlay"] == {
        "url": "/api/product/v1/artifacts/art_preview/content",
        "bounds": [100.0, 39.9, 100.1, 40.0],
        "opacity": 0.72,
        "color_scale": [[0.0, "#440154"], [7.0, "#fff7bc"]],
    }


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


def test_canonical_binary_artifact_content_is_served_only_from_configured_root(tmp_path) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    preview_path = artifact_root / "lai-preview.png"
    preview_bytes = b"\x89PNG\r\n\x1a\npreview"
    preview_path.write_bytes(preview_bytes)
    outside_path = tmp_path / "outside.png"
    outside_path.write_bytes(preview_bytes)

    store = ArtifactStore(db_path=str(tmp_path / "binary-artifacts.sqlite3"))
    preview_id = store.register(
        "analysis-demo",
        SimpleNamespace(
            pack_name="prosail",
            artifact_type="lai_preview",
            title="LAI preview",
            uri=str(preview_path),
            content="summary",
        ),
    )
    outside_id = store.register(
        "analysis-demo",
        SimpleNamespace(
            pack_name="prosail",
            artifact_type="lai_preview",
            title="Outside preview",
            uri=str(outside_path),
            content="must not bypass path validation",
        ),
    )
    app = FastAPI()
    app.state.product_artifact_store = store
    app.state.product_artifact_root = artifact_root
    app.include_router(build_canonical_router(), prefix="/api/product/v1")
    client = TestClient(app)

    metadata = client.get(f"/api/product/v1/artifacts/{preview_id}")
    response = client.get(f"/api/product/v1/artifacts/{preview_id}/content")
    blocked = client.get(f"/api/product/v1/artifacts/{outside_id}/content")

    assert metadata.json()["view_url"].endswith(f"/{preview_id}/content")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == preview_bytes
    assert blocked.status_code == 404
    store._db.close()


def test_lai_sse_replays_persisted_events_after_last_event_id(tmp_path) -> None:
    store = LaiAnalysisStore(db_path=tmp_path / "lai-events.sqlite3")
    created = store.create(CreateLaiAnalysisRequest(
        aoi=AoiGeometry(geometry=GeoJsonGeometry(
            type="Polygon",
            coordinates=[[[100.0, 39.9], [100.1, 39.9], [100.1, 40.0], [100.0, 39.9]]],
        )),
        imagery_item_id="S2-demo",
    ))
    first = store.push_event(created.analysis_id, {
        "kind": "progress",
        "stage": "imagery",
        "detail": "first event",
    })
    _, second = store.update_and_push_event(
        created.analysis_id,
        {"kind": "result", "stage": "completed", "detail": "second event"},
        status="completed",
        stage="completed",
    )
    app = FastAPI()
    app.state.lai_analysis_store = store
    app.include_router(build_canonical_router(), prefix="/api/product/v1")

    response = TestClient(app).get(
        f"/api/product/v1/lai-analyses/{created.analysis_id}/events",
        headers={"Last-Event-ID": first["event_id"]},
    )

    assert response.status_code == 200
    assert f"id: {second['event_id']}" in response.text
    assert "second event" in response.text
    assert "first event" not in response.text
    store._db.close()


def test_lai_analysis_rejects_missing_or_tampered_imagery_snapshot_before_creation(tmp_path) -> None:
    class RejectingProvider:
        def get_item(self, item_id: str) -> dict:
            return {"id": item_id}

        def validate_selection(self, snapshot, feature, aoi_geometry):
            raise ImagerySearchError("snapshot token mismatch")

    analysis_store = LaiAnalysisStore(db_path=tmp_path / "selection.sqlite3")
    artifact_store = ArtifactStore(db_path=str(tmp_path / "selection-artifacts.sqlite3"))
    app = FastAPI()
    app.state.lai_analysis_store = analysis_store
    app.state.product_artifact_store = artifact_store
    app.state.sentinel_stac_provider = RejectingProvider()
    app.include_router(build_canonical_router(), prefix="/api/product/v1")
    client = TestClient(app)
    base_body = {
        "aoi": {"geometry": {
            "type": "Polygon",
            "coordinates": [[[100.0, 39.9], [100.1, 39.9], [100.1, 40.0], [100.0, 39.9]]],
        }},
        "imagery_item_id": "S2-demo",
    }

    missing = client.post("/api/product/v1/lai-analyses", json=base_body)
    tampered = client.post("/api/product/v1/lai-analyses", json={
        **base_body,
        "imagery_snapshot": {
            "item_id": "S2-demo",
            "collection": "sentinel-2-l2a",
            "acquired_at": "2026-07-01T00:00:00Z",
            "selection_token": "forged",
        },
    })

    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "INVALID_REFERENCE"
    assert tampered.status_code == 400
    assert tampered.json()["error"]["detail"]["reason"] == "snapshot token mismatch"
    assert analysis_store._db.execute("SELECT COUNT(*) FROM product_lai_analyses").fetchone()[0] == 0
    analysis_store._db.close()
    artifact_store._db.close()


def test_canonical_lai_create_worker_sse_and_artifacts_end_to_end(tmp_path, monkeypatch) -> None:
    class VerifiedProvider:
        def get_item(self, item_id: str) -> dict:
            return {"id": item_id, "properties": {"datetime": "2026-07-01T00:00:00Z"}}

        def validate_selection(self, snapshot, feature, aoi_geometry):
            assert feature["id"] == snapshot.item_id
            assert aoi_geometry["type"] == "Polygon"
            return snapshot

    artifact_root = tmp_path / "artifacts"

    def fake_read(*, output_path, progress_callback, target_resolution_m, **_kwargs):
        assert target_resolution_m == 20
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"reflectance")
        progress_callback("five bands ready", 100)
        return output_path

    def fake_report(*, artifact_output_dir, progress_callback, **_kwargs):
        output_dir = Path(artifact_output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        report = output_dir / "report.html"
        raster = output_dir / "lai.tif"
        preview = output_dir / "preview.png"
        report.write_text("<!doctype html><html><body>LAI report</body></html>", encoding="utf-8")
        raster.write_bytes(b"TIFF")
        preview.write_bytes(b"\x89PNG\r\n\x1a\npreview")
        progress_callback(1, 1)
        payload = {
            "report_path": str(report),
            "lai_raster_path": str(raster),
            "lai_preview_path": str(preview),
            "bounds_wgs84": [100.0, 39.9, 100.1, 40.0],
            "color_scale": [[0.0, "#440154"], [7.0, "#fff7bc"]],
        }
        artifacts = [
            PackArtifactView(pack_name="prosail", artifact_type="lai_html_report", title="report", uri=str(report)),
            PackArtifactView(pack_name="prosail", artifact_type="lai_raster", title="raster", uri=str(raster)),
            PackArtifactView(pack_name="prosail", artifact_type="lai_preview", title="preview", uri=str(preview)),
        ]
        return ObservationV2(source="prosail", status="success", summary="complete", payload=payload), artifacts

    monkeypatch.setattr("api.canonical.router.read_prosail_reflectance_aoi", fake_read)
    monkeypatch.setattr("api.canonical.router.run_lai_html_report", fake_report)
    analysis_store = LaiAnalysisStore(db_path=tmp_path / "e2e.sqlite3")
    artifact_store = ArtifactStore(db_path=str(tmp_path / "e2e.sqlite3"))
    app = FastAPI()
    app.state.lai_analysis_store = analysis_store
    app.state.product_artifact_store = artifact_store
    app.state.product_artifact_root = artifact_root
    app.state.sentinel_stac_provider = VerifiedProvider()
    app.include_router(build_canonical_router(), prefix="/api/product/v1")
    client = TestClient(app)
    snapshot = ImageryCandidate(
        item_id="S2-e2e",
        acquired_at="2026-07-01T00:00:00Z",
        coverage_percent=100,
        selection_token="server-token",
        asset_fingerprint="asset-v1",
    )

    created = client.post("/api/product/v1/lai-analyses", json={
        "aoi": {"geometry": {
            "type": "Polygon",
            "coordinates": [[[100.0, 39.9], [100.1, 39.9], [100.1, 40.0], [100.0, 39.9]]],
        }},
        "imagery_item_id": snapshot.item_id,
        "imagery_snapshot": snapshot.model_dump(mode="json"),
    })

    assert created.status_code == 202
    analysis_id = created.json()["analysis_id"]
    streamed = client.get(f"/api/product/v1/lai-analyses/{analysis_id}/events")
    event_payloads = [
        json.loads(line.removeprefix("data: "))
        for line in streamed.text.splitlines()
        if line.startswith("data: ")
    ]
    final = client.get(f"/api/product/v1/lai-analyses/{analysis_id}").json()

    assert streamed.status_code == 200
    assert event_payloads[-1]["kind"] == "result"
    assert [item["sequence"] for item in event_payloads] == list(range(1, len(event_payloads) + 1))
    assert final["status"] == "completed"
    assert len(final["artifact_ids"]) == 4
    assert final["result"]["imagery_provenance"]["item_id"] == "S2-e2e"
    assert final["result"]["map_overlay"]["bounds"] == [100.0, 39.9, 100.1, 40.0]

    report_id = next(
        artifact_id for artifact_id in final["artifact_ids"]
        if artifact_store.get(artifact_id).artifact_type == "lai_html_report"
    )
    preview_id = next(
        artifact_id for artifact_id in final["artifact_ids"]
        if artifact_store.get(artifact_id).artifact_type == "lai_preview"
    )
    assert client.get(f"/api/product/v1/artifacts/{report_id}/render").status_code == 200
    preview_response = client.get(f"/api/product/v1/artifacts/{preview_id}/content")
    assert preview_response.status_code == 200
    assert preview_response.content.startswith(b"\x89PNG")
    analysis_store.close_store()
    artifact_store.close()
