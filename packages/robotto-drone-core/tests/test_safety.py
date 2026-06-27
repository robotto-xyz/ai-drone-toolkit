from __future__ import annotations

import pytest

from robotto_drone_core import safety


def test_simulation_gate_accepts_local_sitl_addresses():
    accepted = [
        "udpin://0.0.0.0:14540",
        "udp://:14540",
        "udp://127.0.0.1:14540",
        "udp://localhost:14540",
    ]

    for address in accepted:
        result = safety.check_simulation_only(address)
        assert result["ok"] is True
        assert result["refused"] is False


@pytest.mark.parametrize(
    "address",
    [
        "serial:///dev/ttyUSB0:57600",
        "tcp://192.168.1.20:5760",
        "udp://192.168.1.20:14540",
        "udpin://0.0.0.0:14550",
    ],
)
def test_simulation_gate_refuses_non_local_or_wrong_port(address):
    result = safety.check_simulation_only(address)

    assert result["ok"] is False
    assert result["refused"] is True
    assert "Simulation-only" in result["reason"]


def test_simulation_gate_cannot_be_disabled():
    result = safety.check_simulation_only(
        "udpin://0.0.0.0:14540",
        simulation_only=False,
    )

    assert result["ok"] is False
    assert result["refused"] is True
    assert "SIMULATION_ONLY" in result["reason"]


def test_altitude_refuses_excessive_request():
    result = safety.clamp_altitude(5000)

    assert result["ok"] is False
    assert result["refused"] is True
    assert "MAX_ALT_M=50" in result["reason"]


def test_altitude_accepts_safe_request():
    result = safety.clamp_altitude(15)

    assert result == {"ok": True, "refused": False, "altitude_m": 15}


def test_geofence_refuses_out_of_radius_goto():
    result = safety.check_geofence(201, 0)

    assert result["ok"] is False
    assert result["refused"] is True
    assert "GEOFENCE_RADIUS_M=200" in result["reason"]


def test_geofence_accepts_inside_radius_goto():
    result = safety.check_geofence(120, 160)

    assert result["ok"] is True
    assert result["radius_m"] == 200


def test_speed_refuses_over_limit():
    result = safety.check_speed(12)

    assert result["ok"] is False
    assert result["refused"] is True
    assert "MAX_SPEED_MS=10" in result["reason"]


def test_arming_preconditions_surface_missing_health():
    result = safety.check_arming_preconditions(
        is_global_position_ok=True,
        is_home_position_ok=False,
    )

    assert result["ok"] is False
    assert result["refused"] is True
    assert "home position" in result["reason"]


def test_arming_preconditions_accept_healthy_position():
    result = safety.check_arming_preconditions(
        is_global_position_ok=True,
        is_home_position_ok=True,
    )

    assert result["ok"] is True
