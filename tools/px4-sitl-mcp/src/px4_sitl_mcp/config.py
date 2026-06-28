"""Configuration for the PX4 SITL command server."""

from __future__ import annotations

from robotto_drone_core.safety import SafetyLimits

DEFAULT_SIM_ADDRESS = "udpin://0.0.0.0:14540"
# The single-drone tools (connect_sim, takeoff, goto, ...) and the fleet tools
# address the SAME first drone. Keeping DEFAULT_DRONE_ID == "drone-1" makes them
# one namespace instead of two, so there is no separate "default" entry pointed
# at the same 14540 endpoint as "drone-1".
DEFAULT_DRONE_ID = "drone-1"
DEFAULT_MULTI_DRONE_ADDRESSES = {
    "drone-1": "udpin://0.0.0.0:14540",
    "drone-2": "udpin://0.0.0.0:14541",
    "drone-3": "udpin://0.0.0.0:14542",
}
DEFAULT_YAW_DEG = 0.0
DEFAULT_CONNECT_TIMEOUT_S = 30.0
DEFAULT_REACH_TIMEOUT_S = 60.0

# PX4's onboard position controller (used by goto_location) settles near a
# waypoint, not exactly on it. A tight 2 m horizontal tolerance can never
# trigger if the vehicle parks 2-4 m out, causing false timeouts on waypoints
# the drone actually reached. Use a more realistic settling radius.
GOTO_HORIZONTAL_TOLERANCE_M = 4.0
GOTO_VERTICAL_TOLERANCE_M = 1.5

# PX4's auto-takeoff climbs to the commanded altitude and then settles slightly
# ABOVE it (observed ~1.5 m above a 15 m command, holding at ~16.5 m). An
# abs(current - target) <= 1 m check never triggers and the takeoff falsely
# times out. Treat takeoff as "reached" once the drone has climbed to within
# this margin BELOW the target; overshoot above the target is expected and fine.
TAKEOFF_REACH_TOLERANCE_M = 1.0

SAFETY_LIMITS = SafetyLimits(
    max_alt_m=50.0,
    geofence_radius_m=200.0,
    max_speed_ms=10.0,
)
