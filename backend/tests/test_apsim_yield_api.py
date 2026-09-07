from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.canonical.router import install_canonical_product_api
from v2.tools.apsim_report_handler import get_apsim_demo_db_path


@pytest.mark.skipif(
    not get_apsim_demo_db_path().is_file(),
    reason="Bundled APSIM Wheat validation database is unavailable",
)
def test_demo_yield_report_is_generated_and_renderable(tmp_path) -> None:
    app = FastAPI()
    install_canonical_product_api(
        app,
        db_path=str(tmp_path / "product.sqlite3"),
        auth_required=True,
        auth_token="product-secret",
    )
    headers = {"Authorization": "Bearer product-secret"}

    with TestClient(app) as client:
        response = client.post(
            "/api/product/v1/apsim/yield-reports",
            headers=headers,
            json={
                "mode": "demo",
                "crop_type": "maize",
                "region": "henan",
                "start_year": 2024,
                "end_year": 2025,
                "cultivar": "",
                "sowing_date": "",
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["mode"] == "demo"
        assert payload["metrics"] == {
            "estimated_yield_t_ha": 6.51,
            "peak_lai": 5.591,
            "max_biomass_g_m2": 1399.6,
            "simulation_days": 241,
        }
        assert payload["parameters"]["crop_type"] == "wheat"
        assert payload["parameters"]["cultivar"] == "Hartog"
        assert payload["artifact"]["kind"] == "apsim_report"

        render = client.get(payload["artifact"]["view_url"], headers=headers)
        assert render.status_code == 200
        assert render.headers["content-type"].startswith("text/html")
        assert "APSIM 作物生长模拟报告" in render.text
        assert "6.510" in render.text


def test_yield_report_rejects_reversed_year_range(tmp_path) -> None:
    app = FastAPI()
    install_canonical_product_api(app, db_path=str(tmp_path / "product.sqlite3"))

    with TestClient(app) as client:
        response = client.post(
            "/api/product/v1/apsim/yield-reports",
            json={
                "mode": "simulation",
                "crop_type": "wheat",
                "region": "henan",
                "start_year": 2025,
                "end_year": 2024,
            },
        )

    assert response.status_code == 422
    assert "结束年份不能早于开始年份" in response.json()["error"]["message"]
