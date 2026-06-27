"""Pure safety checks for simulated drone-command tools.

The functions in this module know nothing about MCP or MAVSDK. They return
plain JSON-serializable dicts so tools can pass clear refusals back to an LLM
without leaking library exceptions or ambiguous "command denied" messages.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import Any
from urllib.parse import urlparse


SIMULATION_ONLY = True
DEFAULT_SITL_PORT = 14540


@dataclass(frozen=True)
class SafetyLimits:
    """Configurable bounds for simulation-only command tools."""

    max_alt_m: float = 50.0
    geofence_radius_m: float = 200.0
    max_speed_ms: float = 10.0


def ok(**data: Any) -> dict[str, Any]:
    """Return a structured success result."""

    return {"ok": True, "refused": False, **data}


def refused(reason: str, **data: Any) -> dict[str, Any]:
    """Return a structured refusal an LLM can relay to the user."""

    return {"ok": False, "refused": True, "reason": reason, **data}


def _parse_mavsdk_address(address: str) -> tuple[str, str | None, int | None]:
    """Parse MAVSDK system addresses such as ``udpin://0.0.0.0:14540``.

    MAVSDK examples also use compact forms like ``udp://:14540`` where the host
    is omitted. Treat that as a local bind address.
    """

    parsed = urlparse(address)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc
    if not scheme:
        return "", None, None

    if ":" in netloc:
        host_part, port_part = netloc.rsplit(":", 1)
    else:
        host_part, port_part = netloc, ""

    host = host_part or "0.0.0.0"
    try:
        port = int(port_part) if port_part else None
    except ValueError:
        port = None

    return scheme, host.lower(), port


def check_simulation_only(
    address: str,
    *,
    simulation_only: bool = SIMULATION_ONLY,
    sitl_port: int = DEFAULT_SITL_PORT,
) -> dict[str, Any]:
    """Verify a MAVSDK address targets a local PX4 SITL endpoint.

    Commanding real aircraft is out of scope for this repository. This gate is
    deliberately a code-level invariant: when ``simulation_only`` is true, only
    UDP localhost-style SITL endpoints on ``sitl_port`` are accepted.
    """

    if not simulation_only:
        return refused("SIMULATION_ONLY must remain enabled in this repository")

    scheme, host, port = _parse_mavsdk_address(address)
    allowed_schemes = {"udp", "udpin", "udpout"}
    allowed_hosts = {"0.0.0.0", "127.0.0.1", "::1", "localhost"}

    if scheme not in allowed_schemes:
        return refused(
            f"Simulation-only mode refuses non-UDP MAVSDK address: {address}"
        )
    if host not in allowed_hosts:
        return refused(
            "Simulation-only mode refuses non-localhost MAVSDK address: "
            f"{address}"
        )
    if port != sitl_port:
        return refused(
            f"Simulation-only mode expects PX4 SITL port {sitl_port}, got {port}"
        )

    return ok(address=address, host=host, port=port)


def clamp_altitude(
    requested_m: float,
    limits: SafetyLimits = SafetyLimits(),
) -> dict[str, Any]:
    """Validate a requested relative altitude in meters."""

    if requested_m <= 0:
        return refused(f"Requested altitude {requested_m:g} m must be positive")
    if requested_m > limits.max_alt_m:
        return refused(
            f"Requested {requested_m:g} m exceeds MAX_ALT_M={limits.max_alt_m:g}",
            requested_m=requested_m,
            max_alt_m=limits.max_alt_m,
        )
    return ok(altitude_m=requested_m)


def check_geofence(
    north_m: float,
    east_m: float,
    limits: SafetyLimits = SafetyLimits(),
) -> dict[str, Any]:
    """Validate a horizontal meters-from-home offset against the geofence."""

    radius_m = hypot(north_m, east_m)
    if radius_m > limits.geofence_radius_m:
        return refused(
            "Requested goto is outside GEOFENCE_RADIUS_M="
            f"{limits.geofence_radius_m:g}",
            north_m=north_m,
            east_m=east_m,
            radius_m=radius_m,
            geofence_radius_m=limits.geofence_radius_m,
        )
    return ok(north_m=north_m, east_m=east_m, radius_m=radius_m)


def check_speed(
    requested_ms: float,
    limits: SafetyLimits = SafetyLimits(),
) -> dict[str, Any]:
    """Validate a requested speed in meters per second."""

    if requested_ms <= 0:
        return refused(f"Requested speed {requested_ms:g} m/s must be positive")
    if requested_ms > limits.max_speed_ms:
        return refused(
            f"Requested {requested_ms:g} m/s exceeds MAX_SPEED_MS="
            f"{limits.max_speed_ms:g}",
            requested_ms=requested_ms,
            max_speed_ms=limits.max_speed_ms,
        )
    return ok(speed_ms=requested_ms)


def check_arming_preconditions(
    *,
    is_global_position_ok: bool,
    is_home_position_ok: bool,
) -> dict[str, Any]:
    """Validate the PX4 health preconditions needed before arming."""

    missing: list[str] = []
    if not is_global_position_ok:
        missing.append("global position")
    if not is_home_position_ok:
        missing.append("home position")
    if missing:
        return refused(
            "Cannot arm until PX4 reports healthy " + " and ".join(missing),
            is_global_position_ok=is_global_position_ok,
            is_home_position_ok=is_home_position_ok,
        )
    return ok(
        is_global_position_ok=is_global_position_ok,
        is_home_position_ok=is_home_position_ok,
    )
