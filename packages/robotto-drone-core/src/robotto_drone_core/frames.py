"""Coordinate-frame and altitude helpers for drone command tools.

PX4 and MAVSDK mix conventions that are easy to get wrong: PX4 commonly uses
NED (North-East-Down), humans tend to speak ENU-ish offsets, and MAVSDK's
``goto_location`` expects absolute AMSL altitude. Keep those conversions here
so every command tool uses the same tested logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import asin, atan2, cos, degrees, radians, sin, sqrt

EARTH_RADIUS_M = 6_378_137.0


@dataclass(frozen=True)
class NEDPosition:
    """Position in North-East-Down meters."""

    north_m: float
    east_m: float
    down_m: float


@dataclass(frozen=True)
class ENUPosition:
    """Position in East-North-Up meters."""

    east_m: float
    north_m: float
    up_m: float


def ned_to_enu(north_m: float, east_m: float, down_m: float) -> ENUPosition:
    """Convert NED meters to ENU meters. In NED, down is positive."""

    return ENUPosition(east_m=east_m, north_m=north_m, up_m=-down_m)


def enu_to_ned(east_m: float, north_m: float, up_m: float) -> NEDPosition:
    """Convert ENU meters to NED meters. In NED, down is positive."""

    return NEDPosition(north_m=north_m, east_m=east_m, down_m=-up_m)


def relative_to_amsl(relative_altitude_m: float, home_amsl_m: float) -> float:
    """Convert height above home to absolute AMSL altitude."""

    return home_amsl_m + relative_altitude_m


def amsl_to_relative(absolute_altitude_m: float, home_amsl_m: float) -> float:
    """Convert absolute AMSL altitude to height above home."""

    return absolute_altitude_m - home_amsl_m


def offset_to_latlon(
    home_lat_deg: float,
    home_lon_deg: float,
    north_m: float,
    east_m: float,
) -> tuple[float, float]:
    """Convert meters-from-home north/east offsets to latitude/longitude.

    Uses the standard great-circle destination formula. It is accurate enough
    for the small geofenced offsets used by the SITL command tools.
    """

    distance_m = sqrt(north_m**2 + east_m**2)
    if distance_m == 0:
        return home_lat_deg, home_lon_deg

    bearing_rad = atan2(east_m, north_m)
    lat1 = radians(home_lat_deg)
    lon1 = radians(home_lon_deg)
    angular_distance = distance_m / EARTH_RADIUS_M

    lat2 = asin(
        sin(lat1) * cos(angular_distance)
        + cos(lat1) * sin(angular_distance) * cos(bearing_rad)
    )
    lon2 = lon1 + atan2(
        sin(bearing_rad) * sin(angular_distance) * cos(lat1),
        cos(angular_distance) - sin(lat1) * sin(lat2),
    )

    return degrees(lat2), degrees(lon2)


def latlon_to_offset(
    home_lat_deg: float,
    home_lon_deg: float,
    lat_deg: float,
    lon_deg: float,
) -> tuple[float, float]:
    """Approximate north/east meters from home for small local offsets."""

    home_lat_rad = radians(home_lat_deg)
    lat_delta_rad = radians(lat_deg - home_lat_deg)
    lon_delta_rad = radians(lon_deg - home_lon_deg)
    north_m = lat_delta_rad * EARTH_RADIUS_M
    east_m = lon_delta_rad * EARTH_RADIUS_M * cos(home_lat_rad)
    return north_m, east_m


def reached_target(
    *,
    current_north_m: float,
    current_east_m: float,
    current_altitude_m: float,
    target_north_m: float,
    target_east_m: float,
    target_altitude_m: float,
    horizontal_tolerance_m: float = 2.0,
    vertical_tolerance_m: float = 1.0,
) -> bool:
    """Return true when the current local offset is close enough to target."""

    horizontal_error_m = sqrt(
        (current_north_m - target_north_m) ** 2
        + (current_east_m - target_east_m) ** 2
    )
    vertical_error_m = abs(current_altitude_m - target_altitude_m)
    return (
        horizontal_error_m <= horizontal_tolerance_m
        and vertical_error_m <= vertical_tolerance_m
    )
