from __future__ import annotations

import httpx
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from infra.imagery.stac_provider import SentinelStacProvider, SentinelStacSettings
from infra.imagery.aoi_band_reader import (
    AoiBandReadError,
    _band_read_error_message,
    read_prosail_reflectance_aoi,
    resolve_band_asset,
)
from schemas.spatial import AoiGeometry, GeoJsonGeometry, ImagerySearchRequest


def _request() -> ImagerySearchRequest:
    return ImagerySearchRequest(
        aoi=AoiGeometry(geometry=GeoJsonGeometry(type="Polygon", coordinates=[[[100, 38], [101, 38], [101, 39], [100, 38]]])),
        start_date="2025-05-01",
        end_date="2025-05-31",
    )


def test_stac_provider_maps_and_recommends_lowest_cloud_candidate(monkeypatch) -> None:
    def fake_post(*args, **kwargs):
        request = httpx.Request("POST", "https://example.test/search")
        return httpx.Response(200, request=request, json={"features": [
            {"id": "cloudy", "collection": "sentinel-2-l2a", "properties": {"datetime": "2025-05-30T10:00:00Z", "eo:cloud_cover": 12.0}, "assets": {}},
            {"id": "clear", "collection": "sentinel-2-l2a", "properties": {"datetime": "2025-05-28T10:00:00Z", "eo:cloud_cover": 2.0, "platform": "sentinel-2b"}, "assets": {"thumbnail": {"href": "https://example.test/thumb.jpg"}}},
        ]})

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = SentinelStacProvider(SentinelStacSettings(search_url="https://example.test/search"))

    candidates = provider.search(_request())

    assert [candidate.item_id for candidate in candidates] == ["clear", "cloudy"]
    assert candidates[0].is_recommended is True
    assert candidates[0].thumbnail_url == "https://example.test/thumb.jpg"


def test_planetary_computer_item_signs_required_assets_with_one_token(monkeypatch) -> None:
    assets = {
        band: {
            "href": f"https://sentinel2l2a01.blob.core.windows.net/sentinel2-l2/item/{band}.tif"
        }
        for band in ("B02", "B03", "B04", "B07", "B08")
    }

    def fake_post(*args, **kwargs):
        request = httpx.Request("POST", "https://planetarycomputer.test/search")
        return httpx.Response(200, request=request, json={"features": [{"id": "item", "assets": assets}]})

    token_calls: list[str] = []

    def fake_get(url, *args, **kwargs):
        token_calls.append(url)
        request = httpx.Request("GET", url)
        return httpx.Response(200, request=request, json={"token": "signed-token"})

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", fake_get)
    provider = SentinelStacProvider(SentinelStacSettings(
        search_url="https://planetarycomputer.test/search",
        asset_token_url="https://planetarycomputer.test/token",
    ))

    item = provider.get_item("item")

    assert len(token_calls) == 1
    assert token_calls[0].endswith("/sentinel2l2a01/sentinel2-l2")
    assert all(item["assets"][band]["href"].endswith("?signed-token") for band in assets)


def test_band_asset_resolution_accepts_standard_stac_variants() -> None:
    assert resolve_band_asset({"b02": {"href": "https://example.test/b02.tif"}}, "B02").endswith("b02.tif")
    assert resolve_band_asset({"blue": {"href": "https://example.test/blue.tif"}}, "B02").endswith("blue.tif")
    assert resolve_band_asset({"rededge3": {"href": "https://example.test/rededge3.tif"}}, "B07").endswith("rededge3.tif")
    assert resolve_band_asset({"nir": {"href": "https://example.test/nir.tif"}}, "B08").endswith("nir.tif")
    with pytest.raises(AoiBandReadError):
        resolve_band_asset({}, "B08")


def test_aoi_band_reader_reports_real_progress(tmp_path) -> None:
    assets: dict[str, dict[str, str]] = {}
    profile = {
        "driver": "GTiff",
        "height": 4,
        "width": 4,
        "count": 1,
        "dtype": "uint16",
        "crs": "EPSG:4326",
        "transform": from_origin(100.0, 39.0, 0.01, 0.01),
        "nodata": 0,
    }
    for index, band in enumerate(("B02", "B03", "B04", "B07", "B08"), start=1):
        band_path = tmp_path / f"{band}.tif"
        with rasterio.open(band_path, "w", **profile) as dataset:
            dataset.write(np.full((1, 4, 4), index * 1000, dtype="uint16"))
        assets[band] = {"href": str(band_path)}

    updates: list[tuple[str, int]] = []
    output = read_prosail_reflectance_aoi(
        item={"assets": assets},
        geometry={
            "type": "Polygon",
            "coordinates": [[[100.005, 38.965], [100.035, 38.965], [100.035, 38.995], [100.005, 38.995], [100.005, 38.965]]],
        },
        output_path=tmp_path / "reflectance.tif",
        progress_callback=lambda detail, percent: updates.append((detail, percent)),
    )

    assert output.exists()
    assert updates[0][1] == 0
    assert updates[-1] == ("AOI 反射率影像准备完成", 100)
    assert all(current[1] <= following[1] for current, following in zip(updates, updates[1:]))
    assert all(any(band in detail for detail, _ in updates) for band in ("B02", "B03", "B04", "B07", "B08"))
    with rasterio.open(output) as dataset:
        assert dataset.count == 5
        assert dataset.dtypes == ("float32",) * 5


def test_band_read_error_is_actionable_and_hides_signed_url() -> None:
    error = RuntimeError("HTTP 403 Forbidden: https://example.test/B02.tif?token=super-secret")

    message = _band_read_error_message("B02", error)

    assert "链接已过期" in message
    assert "super-secret" not in message
