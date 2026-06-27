from __future__ import annotations

import pytest

from robotto_drone_core import frames


def test_ned_to_enu_down_becomes_negative_up():
    enu = frames.ned_to_enu(north_m=10, east_m=20, down_m=5)

    assert enu.east_m == 20
    assert enu.north_m == 10
    assert enu.up_m == -5


def test_enu_to_ned_up_becomes_negative_down():
    ned = frames.enu_to_ned(east_m=20, north_m=10, up_m=5)

    assert ned.north_m == 10
    assert ned.east_m == 20
    assert ned.down_m == -5


def test_relative_and_amsl_conversion_round_trip():
    home_amsl = 488.2
    relative = 15.0

    absolute = frames.relative_to_amsl(relative, home_amsl)

    assert absolute == pytest.approx(503.2)
    assert frames.amsl_to_relative(absolute, home_amsl) == pytest.approx(relative)


def test_offset_to_latlon_known_small_offsets_at_equator():
    lat, lon = frames.offset_to_latlon(0.0, 0.0, north_m=111.319, east_m=0.0)

    assert lat == pytest.approx(0.001, rel=1e-3)
    assert lon == pytest.approx(0.0, abs=1e-9)


def test_offset_to_latlon_returns_home_for_zero_offset():
    assert frames.offset_to_latlon(47.397742, 8.545594, 0, 0) == (
        47.397742,
        8.545594,
    )


def test_latlon_to_offset_round_trips_small_geofenced_offset():
    home_lat = 47.397742
    home_lon = 8.545594
    target_lat, target_lon = frames.offset_to_latlon(
        home_lat,
        home_lon,
        north_m=50,
        east_m=25,
    )

    north_m, east_m = frames.latlon_to_offset(
        home_lat,
        home_lon,
        target_lat,
        target_lon,
    )

    assert north_m == pytest.approx(50, abs=0.1)
    assert east_m == pytest.approx(25, abs=0.1)


def test_reached_target_uses_horizontal_and_vertical_tolerances():
    assert frames.reached_target(
        current_north_m=49,
        current_east_m=1,
        current_altitude_m=14.5,
        target_north_m=50,
        target_east_m=0,
        target_altitude_m=15,
    )
    assert not frames.reached_target(
        current_north_m=45,
        current_east_m=0,
        current_altitude_m=15,
        target_north_m=50,
        target_east_m=0,
        target_altitude_m=15,
    )
