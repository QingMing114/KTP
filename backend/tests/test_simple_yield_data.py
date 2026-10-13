from datetime import date
from types import SimpleNamespace

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from infra.imagery import power_weather
from infra.imagery import stac_provider
from infra.imagery.season_series import read_ndvi_observation
from runtime.simple_yield import SimpleYieldError


def test_cloud_mask_gets_the_same_asset_signature_as_reflectance(monkeypatch):
    class Response:
        def raise_for_status(self): pass
        def json(self): return {'token': 'test-signature'}
    monkeypatch.setattr(stac_provider.httpx, 'get', lambda *args, **kwargs: Response())
    feature = {'assets': {band: {'href': f'https://test.blob.core.windows.net/container/{band}.tif'} for band in ('B04', 'B08', 'SCL')}}
    signed = stac_provider.SentinelStacProvider()._sign_azure_assets(feature)
    assert all(asset['href'].endswith('?test-signature') for asset in signed['assets'].values())
    assert not feature['assets']['SCL']['href'].endswith('?test-signature')


def test_real_band_math_respects_boa_offset_and_cloud_pixels(tmp_path):
    assets = {}
    for band, value in [('B04', 2000), ('B08', 5000), ('SCL', 4)]:
        path = tmp_path / f'{band}.tif'
        pixels = np.full((10, 10), value, dtype='uint16')
        if band == 'SCL':
            pixels[:2] = 9
        with rasterio.open(path, 'w', driver='GTiff', count=1, width=10, height=10,
                           crs='EPSG:32647', transform=from_origin(0, 200, 20, 20), dtype='uint16') as target:
            target.write(pixels, 1)
        assets[band] = {'href': str(path)}
    from rasterio.warp import transform_geom
    geometry = transform_geom('EPSG:32647', 'EPSG:4326', {'type': 'Polygon', 'coordinates': [[[0, 0], [200, 0], [200, 200], [0, 200], [0, 0]]]})
    provider = SimpleNamespace(get_item=lambda _: {'assets': assets, 'properties': {'s2:processing_baseline': '05.12'}})
    observed = read_ndvi_observation(provider, {'item_id': 'test', 'date': '2025-06-01'}, geometry, tmp_path / 'cache')
    # BOA reflectance is red=0.1 and NIR=0.4, hence NDVI=0.6, not 3/7.
    assert observed['ndvi'] == pytest.approx(0.6)
    assert 0.7 <= observed['valid_fraction'] <= 0.9
    assert observed['radiometry']['B04']['offset'] == -0.1
    assert observed['valid_pixels'] >= 16


def test_power_units_and_missing_values_remain_observable(tmp_path, monkeypatch):
    document = {'parameters': {'ALLSKY_SFC_SW_DWN': {'units': 'MJ/m^2/day'}},
                'properties': {'parameter': {'ALLSKY_SFC_SW_DWN': {'20250601': 20, '20250602': -999}, 'T2M': {'20250601': 15}}}}
    class Response:
        def raise_for_status(self): pass
        def json(self): return document
    monkeypatch.setattr(power_weather.httpx, 'get', lambda *args, **kwargs: Response())
    geometry = {'type': 'Polygon', 'coordinates': [[[100, 38], [100.01, 38], [100.01, 38.01], [100, 38.01], [100, 38]]]}
    rows, provenance = power_weather.fetch_power_weather(geometry, date(2025, 6, 1), date(2025, 6, 2), tmp_path)
    assert rows == {'2025-06-01': {'solar_mj_m2': 20.0, 'temperature_c': 15.0}}
    assert provenance['spatial_support'] == '公开区域格点，非地块测站'
    assert not list(tmp_path.glob('*.json'))
    document['parameters']['ALLSKY_SFC_SW_DWN']['units'] = 'kWh/m²/day'
    with pytest.raises(SimpleYieldError) as error:
        power_weather.fetch_power_weather(geometry, date(2025, 6, 1), date(2025, 6, 2), tmp_path)
    assert error.value.code == 'weather_units'
