"""Pure survey-pattern generation for drone command tools.

Survey planning is reusable domain logic, so it lives in core rather than in an
MCP server. The generated waypoints are meters-from-home offsets and contain no
MAVSDK-specific details.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import safety


@dataclass(frozen=True)
class SurveyWaypoint:
    """A meters-from-home waypoint for a survey path."""

    north_m: float
    east_m: float
    altitude_m: float

    def to_dict(self) -> dict[str, float]:
        return {
            "north_m": self.north_m,
            "east_m": self.east_m,
            "altitude_m": self.altitude_m,
        }


def _axis_values(length_m: float, spacing_m: float) -> list[float]:
    """Return centered axis values that always include both field edges."""

    start = -length_m / 2
    end = length_m / 2
    values = [start]
    current = start + spacing_m
    while current < end:
        values.append(current)
        current += spacing_m
    if values[-1] != end:
        values.append(end)
    return values


def generate_lawnmower(
    width_m: float,
    height_m: float,
    spacing_m: float,
    altitude_m: float,
) -> list[dict[str, float]]:
    """Generate a centered lawnmower path in meters-from-home coordinates.

    `width_m` spans east/west, `height_m` spans north/south, `spacing_m`
    controls the distance between north/south passes, and `altitude_m` is the
    relative altitude above home assigned to every waypoint.
    """

    for name, value in {
        "width_m": width_m,
        "height_m": height_m,
        "spacing_m": spacing_m,
        "altitude_m": altitude_m,
    }.items():
        if value <= 0:
            raise ValueError(f"{name} must be positive")

    north_rows = _axis_values(height_m, spacing_m)
    west_east = (-width_m / 2, width_m / 2)
    east_west = (width_m / 2, -width_m / 2)

    waypoints: list[SurveyWaypoint] = []
    for idx, north_m in enumerate(north_rows):
        east_values = west_east if idx % 2 == 0 else east_west
        for east_m in east_values:
            waypoints.append(
                SurveyWaypoint(
                    north_m=north_m,
                    east_m=east_m,
                    altitude_m=altitude_m,
                )
            )

    return [waypoint.to_dict() for waypoint in waypoints]


def validate_survey_waypoints(
    waypoints: list[dict[str, float]],
    limits: safety.SafetyLimits = safety.SafetyLimits(),
) -> dict[str, Any]:
    """Validate all survey waypoints before any command is issued."""

    for index, waypoint in enumerate(waypoints):
        altitude = safety.clamp_altitude(waypoint["altitude_m"], limits)
        if not altitude["ok"]:
            return {
                **altitude,
                "waypoint_index": index,
                "waypoint": waypoint,
            }
        geofence = safety.check_geofence(
            waypoint["north_m"],
            waypoint["east_m"],
            limits,
        )
        if not geofence["ok"]:
            return {
                **geofence,
                "waypoint_index": index,
                "waypoint": waypoint,
            }
    return safety.ok(num_waypoints=len(waypoints))
