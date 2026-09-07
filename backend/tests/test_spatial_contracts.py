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
        aoi=AoiGeometry(geometry=_geometry()),
        imagery_item_id="S2B_50SMF_20250528",
    )

    assert analysis.parameters.target_resolution_m == 20
    assert analysis.parameters.bands == ["B02", "B03", "B04", "B07", "B08"]
    assert analysis.aoi.source == "drawn"
    assert analysis.aoi.area_hectares is not None


@pytest.mark.parametrize(
    ("coordinates", "message"),
    [
        ([[100.0, 38.0], [100.1, 38.0], [100.1, 38.1], [100.0, 38.1]], "closed"),
        ([[181.0, 38.0], [181.1, 38.0], [181.1, 38.1], [181.0, 38.0]], "WGS84"),
        ([[100.0, 38.0], [100.1, 38.1], [100.0, 38.1], [100.1, 38.0], [100.0, 38.0]], "self-intersect"),
        ([[100.0, 38.0], [100.000001, 38.0], [100.000001, 38.000001], [100.0, 38.0]], "at least"),
        ([[100.0, 38.0], [105.0, 38.0], [105.0, 43.0], [100.0, 38.0]], "exceed"),
    ],
)
def test_backend_rejects_invalid_or_unbounded_aoi(coordinates, message) -> None:
    with pytest.raises(ValidationError, match=message):
        GeoJsonGeometry(type="Polygon", coordinates=[coordinates])


def test_backend_rejects_client_area_that_does_not_match_geometry() -> None:
    with pytest.raises(ValidationError, match="does not match"):
        AoiGeometry(geometry=_geometry(), area_hectares=1.0)


def test_lai_parameters_reject_unimplemented_spatial_options() -> None:
    with pytest.raises(ValidationError):
        CreateLaiAnalysisRequest(
            aoi=AoiGeometry(geometry=_geometry()),
            imagery_item_id="S2-demo",
            parameters={"target_resolution_m": 10},
        )
    with pytest.raises(ValidationError, match="PROSAIL contract"):
        CreateLaiAnalysisRequest(
            aoi=AoiGeometry(geometry=_geometry()),
            imagery_item_id="S2-demo",
            parameters={"bands": ["B02", "B03"]},
        )


def test_imagery_search_rejects_reversed_date_range() -> None:
    with pytest.raises(ValidationError, match="start_date"):
        ImagerySearchRequest(
            aoi=AoiGeometry(geometry=_geometry()),
            start_date="2025-06-01",
            end_date="2025-05-01",
        )


def test_imagery_search_defaults_to_a_ninety_day_window_from_end_date() -> None:
    request = ImagerySearchRequest(
        aoi=AoiGeometry(geometry=_geometry()),
        end_date="2025-06-10",
    )

    assert request.start_date == "2025-03-12"


def test_lai_analysis_state_is_persisted() -> None:
    db_path = Path("var/runtime/test_lai_analysis_store.sqlite3")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    for path in (db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm")):
        path.unlink(missing_ok=True)
    store = LaiAnalysisStore(db_path=db_path)
    created = store.create(CreateLaiAnalysisRequest(aoi=AoiGeometry(geometry=_geometry()), imagery_item_id="S2-demo"))

    updated = store.update(
        created.analysis_id,
        status="completed",
        stage="completed",
        progress_percent=18,
        detail="正在读取 Sentinel B03 波段（2/5）",
        progress_data={"processed_pixels": 512, "current_pixel": 513, "total_pixels": 2048},
        updated_at="2026-07-18T10:00:00+00:00",
    )

    reloaded = LaiAnalysisStore(db_path=db_path)
    assert updated is not None
    assert reloaded.get(created.analysis_id).stage == "completed"
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
        assert event["kind"] == "progress"
        assert event["progress_percent"] == 12
        assert event["analysis_id"] == created.analysis_id
        assert event["sequence"] == 1
        store._db.close()
        stale_loop.close()

    asyncio.run(exercise())


def test_lai_events_are_persisted_with_monotonic_sequences(tmp_path) -> None:
    db_path = tmp_path / "persisted-events.sqlite3"
    store = LaiAnalysisStore(db_path=db_path)
    created = store.create(
        CreateLaiAnalysisRequest(aoi=AoiGeometry(geometry=_geometry()), imagery_item_id="S2-demo")
    )
    first = store.push_event(created.analysis_id, {"kind": "progress", "detail": "first"})
    _, second = store.update_and_push_event(
        created.analysis_id,
        {"kind": "result", "detail": "done"},
        status="completed",
        stage="completed",
    )

    reloaded = LaiAnalysisStore(db_path=db_path)
    events = reloaded.list_events(created.analysis_id)

    assert [event["sequence"] for event in events] == [1, 2]
    assert [event["event_id"] for event in events] == [first["event_id"], second["event_id"]]
    assert reloaded.event_sequence(created.analysis_id, first["event_id"]) == 1
    store._db.close()
    reloaded._db.close()


def test_lai_store_archives_interrupted_work_after_restart(tmp_path) -> None:
    db_path = tmp_path / "interrupted.sqlite3"
    store = LaiAnalysisStore(db_path=db_path)
    created = store.create(
        CreateLaiAnalysisRequest(aoi=AoiGeometry(geometry=_geometry()), imagery_item_id="S2-demo")
    )
    store.update(created.analysis_id, status="running", stage="inversion", progress_percent=45)

    reloaded = LaiAnalysisStore(db_path=db_path)
    recovered = reloaded.get(created.analysis_id)
    events = reloaded.list_events(created.analysis_id)

    assert recovered is not None
    assert recovered.status == "failed"
    assert recovered.stage == "failed"
    assert recovered.result["reason"] == "service_restarted"
    assert events[-1]["kind"] == "error"
    assert events[-1]["data"]["reason"] == "service_restarted"
    store._db.close()
    reloaded._db.close()
