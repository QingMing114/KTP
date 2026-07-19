from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import pytest
from pydantic import ValidationError

from runtime.farm_store import FarmStore
from runtime.lai_analysis_store import LaiAnalysisStore
from schemas.spatial import AoiGeometry, CreateLaiAnalysisRequest, GeoJsonGeometry, ImagerySearchRequest


def _geometry() -> GeoJsonGeometry:
    return GeoJsonGeometry(
        type="Polygon",
        coordinates=[[[100.0, 38.0], [100.1, 38.0], [100.1, 38.1], [100.0, 38.0]]],
    )


def test_demo_farms_are_loadable_geojson_navigation_presets() -> None:
    farms = FarmStore().list_farms()

    assert [farm.farm_id for farm in farms] == ["farm-heihe", "farm-yongchang", "farm-wuwei"]
    assert all(farm.is_demo and farm.geometry.type == "Polygon" for farm in farms)


def test_analysis_requires_an_explicit_imagery_item() -> None:
    analysis = CreateLaiAnalysisRequest(
        aoi=AoiGeometry(geometry=_geometry(), area_hectares=12.4),
        imagery_item_id="S2B_50SMF_20250528",
    )

    assert analysis.parameters.target_resolution_m == 20
    assert analysis.aoi.source == "drawn"


def test_imagery_search_rejects_reversed_date_range() -> None:
    with pytest.raises(ValidationError, match="start_date"):
        ImagerySearchRequest(
            aoi=AoiGeometry(geometry=_geometry()),
            start_date="2025-06-01",
            end_date="2025-05-01",
        )


def test_lai_analysis_state_is_persisted() -> None:
    db_path = Path("var/runtime/test_lai_analysis_store.sqlite3")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    for path in (db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm")):
        path.unlink(missing_ok=True)
    store = LaiAnalysisStore(db_path=db_path)
    created = store.create(CreateLaiAnalysisRequest(aoi=AoiGeometry(geometry=_geometry()), imagery_item_id="S2-demo"))

    updated = store.update(
        created.analysis_id,
        status="running",
        stage="imagery",
        progress_percent=18,
        detail="正在读取 Sentinel B03 波段（2/5）",
        progress_data={"processed_pixels": 512, "current_pixel": 513, "total_pixels": 2048},
        updated_at="2026-07-18T10:00:00+00:00",
    )

    reloaded = LaiAnalysisStore(db_path=db_path)
    assert updated is not None
    assert reloaded.get(created.analysis_id).stage == "imagery"
    assert reloaded.get(created.analysis_id).progress_percent == 18
    assert reloaded.get(created.analysis_id).detail == "正在读取 Sentinel B03 波段（2/5）"
    assert reloaded.get(created.analysis_id).progress_data["current_pixel"] == 513
    store._db.close()
    reloaded._db.close()
    for path in (db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm")):
        path.unlink(missing_ok=True)


def test_lai_events_bind_to_the_running_server_loop(tmp_path) -> None:
    async def exercise() -> None:
        stale_loop = asyncio.new_event_loop()
        store = LaiAnalysisStore(db_path=tmp_path / "events.sqlite3", loop=stale_loop)
        created = store.create(
            CreateLaiAnalysisRequest(aoi=AoiGeometry(geometry=_geometry()), imagery_item_id="S2-demo")
        )
        queue = store.queue(created.analysis_id)
        assert queue is not None

        worker = threading.Thread(
            target=lambda: store.push_event(created.analysis_id, {"kind": "progress", "progress_percent": 12})
        )
        worker.start()
        worker.join()

        event = await asyncio.wait_for(queue.get(), timeout=1)
        assert event == {"kind": "progress", "progress_percent": 12}
        store._db.close()
        stale_loop.close()

    asyncio.run(exercise())
