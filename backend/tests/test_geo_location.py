"""AOI coordinates, not the selected farm preset, decide the reported location."""

from runtime.crop_decision import resolve_location
from runtime.geo_location import reverse_geocode

ZOUPING = {
    "type": "Polygon",
    "coordinates": [[
        [117.7960098, 36.9507297], [117.7958331, 36.9480382], [117.8039052, 36.9478264],
        [117.8040377, 36.9505179], [117.7960098, 36.9507297],
    ]],
}
QINGHAI_AOI = {  # 100.00E 38.01N falls in Qinghai, west of the Gansu border
    "type": "Polygon",
    "coordinates": [[[100.0, 38.0], [100.01, 38.0], [100.01, 38.01], [100.0, 38.01], [100.0, 38.0]]],
}


def test_reverse_geocode_major_agricultural_regions():
    assert reverse_geocode(36.95, 117.80)["province"] == "山东省"  # Zouping
    assert reverse_geocode(38.96, 100.37)["province"] == "甘肃省"  # Zhangye
    assert reverse_geocode(23.13, 113.26)["province"] == "广东省"  # Guangzhou
    assert reverse_geocode(43.80, 87.60)["province"] == "新疆维吾尔自治区"  # Urumqi


def test_reverse_geocode_refuses_to_guess_outside_the_mapped_area():
    assert reverse_geocode(35.68, 139.69) is None  # Tokyo
    assert reverse_geocode(None, 117.0) is None


def test_farm_preset_only_applies_inside_its_own_boundary():
    inside = resolve_location("farm-zouping", ZOUPING)
    assert inside["farm_mismatch"] is False
    assert inside["label"] == "山东 · 邹平"
    assert inside["province"] == "山东省"
    assert inside["source"] == "farm_preset+admin_boundary"

    outside = resolve_location("farm-zouping", QINGHAI_AOI)
    assert outside["farm_mismatch"] is True
    assert outside["farm_label"] == "山东 · 邹平"
    assert outside["label"] == "青海省"
    assert outside["source"] == "admin_boundary"


def test_location_without_a_farm_uses_the_aoi_boundary():
    location = resolve_location(None, QINGHAI_AOI)
    assert location["source"] == "admin_boundary"
    assert location["label"] == "青海省"
    assert location["farm_mismatch"] is False
