"""Imagery search tool tests (P1-P5 of the integration guide).

Search is read-only and host-invoked: the endpoint calls the registered tool,
the handler delegates to the single search implementation, and model
visibility stays behind an explicit flag.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.canonical.router import install_canonical_product_api
from infra.imagery.stac_provider import ImagerySearchError
from runtime.imagery_search import search_imagery
from schemas.runtime import ObservationV2
from schemas.spatial import ImageryCandidate, ImagerySearchRequest
from v2.tools.crop_tool import CROP_TOOL_NAME
from v2.tools.imagery_search_tool import (
    IMAGERY_SEARCH_TOOL_NAME,
    ImagerySearchToolInput,
    build_imagery_search_handler,
    build_imagery_search_tool_spec,
    configure_imagery_search_tool,
    register_unavailable_imagery_search_tool,
)
from v2.tools.registry import ToolRegistryV2, ToolUnavailableError

AOI = {
    "type": "Polygon",
    "coordinates": [[[100.0, 38.0], [100.01, 38.0], [100.01, 38.01], [100.0, 38.01], [100.0, 38.0]]],
}


def _request() -> ImagerySearchRequest:
    return ImagerySearchRequest.model_validate(
        {
            "aoi": {"geometry": AOI},
            "start_date": "2026-05-01",
            "end_date": "2026-05-20",
            "max_cloud_cover": 20,
        }
    )


def _candidates() -> list[ImageryCandidate]:
    return [
        ImageryCandidate(
            item_id="S2B-1",
            acquired_at="2026-05-14T00:00:00Z",
            cloud_cover=3.0,
            coverage_percent=99.0,
            is_recommended=True,
        ),
        ImageryCandidate(
            item_id="S2B-2",
            acquired_at="2026-05-10T00:00:00Z",
            cloud_cover=8.0,
            coverage_percent=98.0,
        ),
    ]


class _Provider:
    def __init__(self, items: list[ImageryCandidate] | None = None) -> None:
        self.items = items if items is not None else _candidates()
        self.calls = 0

    def search(self, request: ImagerySearchRequest) -> list[ImageryCandidate]:
        self.calls += 1
        return list(self.items)


def _handler(provider=None, **kwargs):
    provider = provider if provider is not None else _Provider()
    return build_imagery_search_handler(provider_resolver=lambda: provider, **kwargs)


def test_service_returns_candidates_and_a_search_id():
    provider = _Provider()

    outcome = search_imagery(provider, _request())

    assert provider.calls == 1
    assert [item.item_id for item in outcome.items] == ["S2B-1", "S2B-2"]
    assert outcome.search_id


def test_service_rejects_a_missing_provider():
    with pytest.raises(ImagerySearchError, match="not configured"):
        search_imagery(None, _request())


def test_spec_is_read_only_and_host_invoked_by_default():
    spec = build_imagery_search_tool_spec(available=True)

    assert spec.name == IMAGERY_SEARCH_TOOL_NAME
    assert spec.category == "remote_sensing"
    assert spec.surface_visibility == "debug"
    assert spec.safety_level == "safe"
    assert spec.permissions == []
    assert spec.presentation is not None
    assert spec.presentation.result_renderer == "imagery_candidates"
    assert spec.input_schema["additionalProperties"] is False


def test_model_visibility_is_an_explicit_gate():
    assert build_imagery_search_tool_spec(available=True).surface_visibility == "debug"
    assert build_imagery_search_tool_spec(available=True, model_visible=True).surface_visibility == "all"


def test_handler_returns_candidates_and_reports_progress():
    events: list[tuple[str, int]] = []
    handler = _handler()

    observation, artifacts = handler(
        progress_callback=lambda detail, percent: events.append((detail, percent)),
        **ImagerySearchToolInput.model_validate(
            {"aoi": {"geometry": AOI}, "end_date": "2026-05-20"}
        ).model_dump(mode="json"),
    )

    assert observation.status == "success"
    assert [item["item_id"] for item in observation.payload["items"]] == ["S2B-1", "S2B-2"]
    assert observation.payload["search_id"]
    assert observation.summary.startswith("找到 2 景候选影像")
    assert "S2B-1" in observation.summary
    assert artifacts == []
    assert [percent for _, percent in events] == [10, 100]


def test_handler_rejects_a_missing_provider():
    handler = build_imagery_search_handler(provider_resolver=lambda: None)

    with pytest.raises(ImagerySearchError, match="not configured"):
        handler(**ImagerySearchToolInput.model_validate(
            {"aoi": {"geometry": AOI}, "end_date": "2026-05-20"}
        ).model_dump(mode="json"))


def test_configure_registers_a_callable_tool():
    registry = ToolRegistryV2(definitions={})
    configure_imagery_search_tool(registry, provider_resolver=lambda: _Provider())

    observation, _ = registry.invoke(
        tool_name=IMAGERY_SEARCH_TOOL_NAME,
        tool_input=ImagerySearchToolInput.model_validate(
            {"aoi": {"geometry": AOI}, "end_date": "2026-05-20"}
        ).model_dump(mode="json"),
    )

    assert observation.status == "success"
    assert len(observation.payload["items"]) == 2


def test_registry_rejects_an_unconfigured_search_tool():
    registry = ToolRegistryV2(definitions={})
    register_unavailable_imagery_search_tool(registry, reason="no stac provider")

    with pytest.raises(ToolUnavailableError, match="no stac provider"):
        registry.invoke(
            tool_name=IMAGERY_SEARCH_TOOL_NAME,
            tool_input={"aoi": {"geometry": AOI}, "end_date": "2026-05-20"},
        )


def test_canonical_install_registers_both_professional_tools(tmp_path):
    app = FastAPI()
    install_canonical_product_api(app, db_path=str(tmp_path / "product.sqlite3"), auth_required=False)

    names = {spec.name for spec in app.state.tool_registry.list_tools()}
    assert {CROP_TOOL_NAME, IMAGERY_SEARCH_TOOL_NAME} <= names
    assert app.state.tool_registry.get_definition(IMAGERY_SEARCH_TOOL_NAME).spec.availability == "available"


def test_search_endpoint_goes_through_the_registry(tmp_path):
    app = FastAPI()
    install_canonical_product_api(app, db_path=str(tmp_path / "product.sqlite3"), auth_required=False)
    registry = app.state.tool_registry

    def probe(**_kwargs):
        return (
            ObservationV2(
                source=IMAGERY_SEARCH_TOOL_NAME,
                status="success",
                summary="probe",
                payload={"items": [], "search_id": "probe-search"},
            ),
            [],
        )

    registry.register(
        IMAGERY_SEARCH_TOOL_NAME,
        build_imagery_search_tool_spec(available=True),
        probe,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/product/v1/imagery/search",
            json={"aoi": {"geometry": AOI}, "end_date": "2026-05-20"},
        )

    assert response.status_code == 200
    assert response.json()["search_id"] == "probe-search"
    assert response.json()["items"] == []
