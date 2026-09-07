"""Sentinel-2 L2A candidate search through a STAC API.

This adapter only discovers products.  Downloading AOI bands remains a later
analysis-stage responsibility, so a search cannot accidentally trigger large
data transfers.
"""

from __future__ import annotations

import os
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from schemas.spatial import ImageryCandidate, ImagerySearchRequest


class ImagerySearchError(RuntimeError):
    """Raised when the configured STAC service cannot provide a response."""


@dataclass(frozen=True)
class SentinelStacSettings:
    search_url: str = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
    collection: str = "sentinel-2-l2a"
    asset_token_url: str | None = "https://planetarycomputer.microsoft.com/api/sas/v1/token"
    timeout_seconds: float = 30.0
    result_limit: int = 5
    minimum_coverage_percent: float = 95.0
    selection_secret: str = "ktp-local-development-selection-secret"

    @classmethod
    def from_environment(cls) -> "SentinelStacSettings":
        return cls(
            search_url=os.getenv("SENTINEL_STAC_SEARCH_URL", cls.search_url),
            collection=os.getenv("SENTINEL_STAC_COLLECTION", cls.collection),
            asset_token_url=os.getenv("SENTINEL_STAC_ASSET_TOKEN_URL", cls.asset_token_url or "") or None,
            timeout_seconds=float(os.getenv("SENTINEL_STAC_TIMEOUT_SECONDS", str(cls.timeout_seconds))),
            result_limit=int(os.getenv("SENTINEL_STAC_RESULT_LIMIT", str(cls.result_limit))),
            minimum_coverage_percent=float(os.getenv("SENTINEL_MINIMUM_COVERAGE_PERCENT", str(cls.minimum_coverage_percent))),
            selection_secret=os.getenv("SENTINEL_SELECTION_SECRET", cls.selection_secret),
        )


class SentinelStacProvider:
    """Maps STAC FeatureCollections to user-selectable imagery candidates."""

    def __init__(self, settings: SentinelStacSettings | None = None) -> None:
        self._settings = settings or SentinelStacSettings.from_environment()

    def search(self, request: ImagerySearchRequest) -> list[ImageryCandidate]:
        payload = {
            "collections": [request.collection or self._settings.collection],
            "intersects": request.aoi.geometry.model_dump(mode="json"),
            "datetime": f"{request.start_date}T00:00:00Z/{request.end_date}T23:59:59Z",
            "limit": self._settings.result_limit,
            "query": {"eo:cloud_cover": {"lte": request.max_cloud_cover}},
            "sortby": [{"field": "properties.datetime", "direction": "desc"}],
        }
        try:
            response = httpx.post(self._settings.search_url, json=payload, timeout=self._settings.timeout_seconds)
            response.raise_for_status()
            features = response.json().get("features", [])
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise ImagerySearchError(f"Sentinel STAC search is unavailable: {type(exc).__name__}") from exc

        candidates = [
            self._candidate_from_feature(feature, request.collection, request.aoi.geometry.model_dump(mode="json"))
            for feature in features
        ]
        candidates = [
            candidate for candidate in candidates
            if (candidate.coverage_percent or 0) >= self._settings.minimum_coverage_percent
        ]
        candidates.sort(key=lambda item: (item.cloud_cover is None, item.cloud_cover or 0, item.acquired_at), reverse=False)
        if candidates:
            recommended = candidates[0]
            candidates[0] = recommended.model_copy(update={
                "is_recommended": True,
                "recommendation_reason": "候选影像中云量最低，且满足当前 AOI 与时间范围。",
            })
        return candidates[:5]

    def validate_selection(
        self,
        snapshot: ImageryCandidate,
        feature: dict[str, Any],
        aoi_geometry: dict[str, Any],
    ) -> ImageryCandidate:
        """Verify that a submitted selection came from search and still matches STAC."""
        fresh = self._candidate_from_feature(feature, self._settings.collection, aoi_geometry)
        if not snapshot.selection_token or not fresh.selection_token:
            raise ImagerySearchError("Selected imagery snapshot is missing its server selection token")
        snapshot_expected = self._selection_token(snapshot, aoi_geometry)
        if (
            not hmac.compare_digest(snapshot.selection_token, snapshot_expected)
            or not hmac.compare_digest(snapshot.selection_token, fresh.selection_token)
        ):
            raise ImagerySearchError("Selected imagery snapshot does not match the AOI or current STAC item")
        if snapshot.item_id != fresh.item_id or snapshot.collection != fresh.collection:
            raise ImagerySearchError("Selected imagery identity does not match the current STAC item")
        if (fresh.coverage_percent or 0) < self._settings.minimum_coverage_percent:
            raise ImagerySearchError("Selected imagery no longer covers enough of the AOI")
        return fresh

    def get_item(self, item_id: str) -> dict[str, Any]:
        """Fetch the exact item selected by the user before any COG read."""
        try:
            response = httpx.post(self._settings.search_url, json={"collections": [self._settings.collection], "ids": [item_id], "limit": 1}, timeout=self._settings.timeout_seconds)
            response.raise_for_status()
            features = response.json().get("features", [])
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise ImagerySearchError(f"Selected Sentinel item cannot be fetched: {type(exc).__name__}") from exc
        if not features:
            raise ImagerySearchError("Selected Sentinel item is no longer available")
        return self._sign_azure_assets(features[0])

    def _sign_azure_assets(self, feature: dict[str, Any]) -> dict[str, Any]:
        """Apply one Planetary Computer SAS token to the required Azure COG assets."""
        token_base_url = self._settings.asset_token_url
        assets = feature.get("assets") or {}
        required_keys = ("B02", "B03", "B04", "B07", "B08")
        azure_assets: list[tuple[str, dict[str, Any], str, str]] = []
        for key in required_keys:
            asset = assets.get(key)
            href = asset.get("href") if isinstance(asset, dict) else None
            if not isinstance(href, str):
                continue
            parsed = urlparse(href)
            path_parts = parsed.path.lstrip("/").split("/", 1)
            if not parsed.hostname or not parsed.hostname.endswith(".blob.core.windows.net") or not path_parts[0]:
                continue
            azure_assets.append((key, asset, parsed.hostname.split(".", 1)[0], path_parts[0]))

        if not azure_assets or token_base_url is None:
            return feature
        account, container = azure_assets[0][2], azure_assets[0][3]
        try:
            response = httpx.get(
                f"{token_base_url.rstrip('/')}/{quote(account, safe='')}/{quote(container, safe='')}",
                timeout=self._settings.timeout_seconds,
            )
            response.raise_for_status()
            token = response.json().get("token")
            if not isinstance(token, str) or not token:
                raise ValueError("SAS token response is empty")
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise ImagerySearchError(f"Sentinel asset signing is unavailable: {type(exc).__name__}") from exc

        signed_assets = dict(assets)
        for key, asset, asset_account, asset_container in azure_assets:
            if (asset_account, asset_container) != (account, container):
                continue
            href = asset["href"]
            signed_assets[key] = {**asset, "href": f"{href}{'&' if '?' in href else '?'}{token}"}
        return {**feature, "assets": signed_assets}

    def _candidate_from_feature(
        self,
        feature: dict[str, Any],
        default_collection: str,
        aoi_geometry: dict[str, Any],
    ) -> ImageryCandidate:
        properties = feature.get("properties") or {}
        assets = feature.get("assets") or {}
        preview = SentinelStacProvider._asset_href(assets, "thumbnail", "rendered_preview", "visual")
        acquired_at = properties.get("datetime") or properties.get("start_datetime") or ""
        candidate = ImageryCandidate(
            item_id=str(feature.get("id") or ""),
            collection=str(feature.get("collection") or default_collection),
            acquired_at=acquired_at,
            cloud_cover=properties.get("eo:cloud_cover"),
            thumbnail_url=preview,
            preview_url=preview,
            platform=properties.get("platform") or properties.get("constellation"),
            item_version=str(
                properties.get("updated")
                or properties.get("created")
                or properties.get("s2:processing_baseline")
                or ""
            ) or None,
            asset_fingerprint=self._asset_fingerprint(feature),
            coverage_percent=self._coverage_percent(feature, aoi_geometry),
        )
        return candidate.model_copy(update={
            "selection_token": self._selection_token(candidate, aoi_geometry),
        })

    @staticmethod
    def _coverage_percent(feature: dict[str, Any], aoi_geometry: dict[str, Any]) -> float:
        from shapely.geometry import box, shape

        try:
            aoi = shape(aoi_geometry)
            feature_geometry = feature.get("geometry")
            footprint = shape(feature_geometry) if feature_geometry else box(*(feature.get("bbox") or []))
            if not aoi.is_valid or not footprint.is_valid or aoi.area <= 0:
                return 0.0
            coverage = 100.0 * footprint.intersection(aoi).area / aoi.area
            return round(max(0.0, min(100.0, coverage)), 4)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _asset_fingerprint(feature: dict[str, Any]) -> str:
        assets = feature.get("assets") or {}
        entries: list[dict[str, Any]] = []
        for band in ("B02", "B03", "B04", "B07", "B08"):
            asset = assets.get(band) or assets.get(band.lower()) or {}
            href = asset.get("href") if isinstance(asset, dict) else None
            parsed = urlparse(href) if isinstance(href, str) else None
            entries.append({
                "band": band,
                "uri": f"{parsed.scheme}://{parsed.netloc}{parsed.path}" if parsed else None,
                "checksum": asset.get("checksum:multihash") or asset.get("file:checksum") if isinstance(asset, dict) else None,
                "etag": asset.get("etag") if isinstance(asset, dict) else None,
            })
        encoded = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _selection_token(self, candidate: ImageryCandidate, aoi_geometry: dict[str, Any]) -> str:
        payload = {
            "item_id": candidate.item_id,
            "collection": candidate.collection,
            "acquired_at": candidate.acquired_at,
            "cloud_cover": candidate.cloud_cover,
            "coverage_percent": candidate.coverage_percent,
            "platform": candidate.platform,
            "item_version": candidate.item_version,
            "asset_fingerprint": candidate.asset_fingerprint,
            "aoi": aoi_geometry,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hmac.new(self._settings.selection_secret.encode("utf-8"), encoded, hashlib.sha256).hexdigest()

    @staticmethod
    def _asset_href(assets: dict[str, Any], *names: str) -> str | None:
        for name in names:
            asset = assets.get(name)
            if isinstance(asset, dict) and isinstance(asset.get("href"), str):
                return asset["href"]
        return None
