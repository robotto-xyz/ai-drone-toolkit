from __future__ import annotations

import pytest

from px4_sitl_mcp import config
from robotto_drone_core import frames, safety


def test_default_sim_address_passes_gate():
    result = safety.check_simulation_only(config.DEFAULT_SIM_ADDRESS)

    assert result["ok"] is True


def test_goto_validation_refuses_outside_geofence():
    result = safety.check_geofence(250, 0, config.SAFETY_LIMITS)

    assert result["ok"] is False
    assert result["refused"] is True
    assert "GEOFENCE_RADIUS_M=200" in result["reason"]


def test_goto_validation_refuses_excessive_altitude():
    result = safety.clamp_altitude(100, config.SAFETY_LIMITS)

    assert result["ok"] is False
    assert result["refused"] is True
    assert "MAX_ALT_M=50" in result["reason"]


def test_goto_validation_converts_relative_altitude_to_amsl():
    assert frames.relative_to_amsl(15, home_amsl_m=488.2) == pytest.approx(503.2)


def test_goto_validation_converts_meters_from_home_to_latlon():
    lat, lon = frames.offset_to_latlon(
        home_lat_deg=47.397742,
        home_lon_deg=8.545594,
        north_m=50,
        east_m=25,
    )

    north_m, east_m = frames.latlon_to_offset(
        home_lat_deg=47.397742,
        home_lon_deg=8.545594,
        lat_deg=lat,
        lon_deg=lon,
    )

    assert north_m == pytest.approx(50, abs=0.1)
    assert east_m == pytest.approx(25, abs=0.1)
