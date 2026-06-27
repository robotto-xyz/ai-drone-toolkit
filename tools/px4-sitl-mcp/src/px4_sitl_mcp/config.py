"""Configuration for the PX4 SITL command server."""

from __future__ import annotations

from robotto_drone_core.safety import SafetyLimits

DEFAULT_SIM_ADDRESS = "udpin://0.0.0.0:14540"
DEFAULT_YAW_DEG = 0.0
DEFAULT_CONNECT_TIMEOUT_S = 30.0
DEFAULT_REACH_TIMEOUT_S = 60.0
DEFAULT_POLL_INTERVAL_S = 0.25

SAFETY_LIMITS = SafetyLimits(
    max_alt_m=50.0,
    geofence_radius_m=200.0,
    max_speed_ms=10.0,
)
