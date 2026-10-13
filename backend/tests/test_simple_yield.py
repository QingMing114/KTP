"""Physical units, incomplete-season guards and immutable experimental report semantics."""
from datetime import date, timedelta

import pytest

from runtime.simple_yield import SimpleYieldError, estimate_observed_season


def series(start=date(2025, 2, 1), *, winter=False):
    rows, weather = [], {}
    for day in range(360 if winter else 240):
        observed = start + timedelta(days=day)
        # Synthetic known crop cycle with observed bare ground on both sides.
        ndvi = 0.10 if day < 30 or day > (300 if winter else 180) else 0.80
        if winter and 70 <= day <= 160:
            ndvi = 0.10
        weather[observed.isoformat()] = {"solar_mj_m2": 20.0, "temperature_c": 0.0 if winter and 70 <= day <= 160 else 20.0}
        if day % 10 == 0:
            rows.append({"date": observed.isoformat(), "ndvi": ndvi, "valid_pixels": 100, "valid_fraction": 0.9})
    return rows, weather


def test_yield_has_physical_units_and_area_does_not_scale_unit_yield():
    observations, weather = series()
    first = estimate_observed_season(observations, weather, crop="maize", as_of="2025-09-30", area_hectares=8)
    second = estimate_observed_season(observations, weather, crop="maize", as_of="2025-09-30", area_hectares=80)
    # APAR of 20 MJ global radiation × 0.48 PAR × about 0.824 FPAR over
    # roughly 150 days; g/m² -> t/ha makes the result around 20, not 2000.
    assert 15 < first["estimated_yield_t_ha"] < 25
    assert first["estimated_yield_t_ha"] == second["estimated_yield_t_ha"]
    assert first["yield_basis"] == "grain_dry_matter"
    assert first["experimental"] and not first["locally_calibrated"]
    assert first["range_type"] == "parameter_scenarios_not_confidence_interval"
    assert first["parameter_scenario_range_t_ha"][0] < first["estimated_yield_t_ha"] < first["parameter_scenario_range_t_ha"][1]
    assert first["season"]["source"] == "automatically_detected_optical_growth_period"


def test_solar_energy_drives_estimate_and_missing_days_do_not_get_filled():
    observations, weather = series()
    result = estimate_observed_season(observations, weather, crop="spring_wheat", as_of="2025-09-30", area_hectares=8)
    doubled = {key: {**value, "solar_mj_m2": 40.0} for key, value in weather.items()}
    next_result = estimate_observed_season(observations, doubled, crop="spring_wheat", as_of="2025-09-30", area_hectares=8)
    assert next_result["estimated_yield_t_ha"] == pytest.approx(result["estimated_yield_t_ha"] * 2, abs=0.002)
    del weather[result["season"]["start"]]
    with pytest.raises(SimpleYieldError) as error:
        estimate_observed_season(observations, weather, crop="maize", as_of="2025-09-30", area_hectares=8)
    assert error.value.code == "weather_incomplete"


def test_single_image_and_future_observations_cannot_supply_a_crop_cycle():
    observations, weather = series()
    with pytest.raises(SimpleYieldError) as error:
        estimate_observed_season(observations[-1:], weather, crop="maize", as_of="2025-09-30", area_hectares=8)
    assert error.value.code == "insufficient_observations"
    with pytest.raises(SimpleYieldError):
        estimate_observed_season(observations, weather, crop="maize", as_of="2025-02-15", area_hectares=8)


def test_does_not_report_last_years_harvest_when_current_crop_is_still_growing():
    observations, weather = series()
    with pytest.raises(SimpleYieldError) as error:
        estimate_observed_season(observations, weather, crop="maize", as_of="2025-06-15", area_hectares=8)
    assert error.value.code == "season_in_progress"


def test_long_optical_gap_is_not_a_synthetic_season():
    observations, weather = series()
    observations = [row for row in observations if not "2025-04-01" <= row["date"] <= "2025-06-15"]
    with pytest.raises(SimpleYieldError) as error:
        estimate_observed_season(observations, weather, crop="maize", as_of="2025-09-30", area_hectares=8)
    assert error.value.code == "observation_gap"


def test_winter_dormancy_is_joined_using_observed_temperature():
    observations, weather = series(date(2024, 9, 1), winter=True)
    result = estimate_observed_season(observations, weather, crop="winter_wheat", as_of="2025-08-30", area_hectares=8)
    assert result["season"]["start"].startswith("2024-")
    assert result["season"]["end"].startswith("2025-")
    assert result["season"]["days"] > 200


def test_crop_and_quality_guards_are_explicit():
    observations, weather = series()
    with pytest.raises(SimpleYieldError) as error:
        estimate_observed_season(observations, weather, crop="soybean", as_of="2025-09-30", area_hectares=8)
    assert error.value.code == "crop_unsupported"
    with pytest.raises(SimpleYieldError):
        estimate_observed_season([{**row, "valid_fraction": 0.1} for row in observations], weather, crop="maize", as_of="2025-09-30", area_hectares=8)
