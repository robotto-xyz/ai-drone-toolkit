from __future__ import annotations

import pytest

from robotto_drone_core import safety, survey


def test_generate_lawnmower_normal_ordered_pattern():
    waypoints = survey.generate_lawnmower(
        width_m=40,
        height_m=20,
        spacing_m=10,
        altitude_m=15,
    )

    assert waypoints == [
        {"north_m": -10, "east_m": -20, "altitude_m": 15},
        {"north_m": -10, "east_m": 20, "altitude_m": 15},
        {"north_m": 0, "east_m": 20, "altitude_m": 15},
        {"north_m": 0, "east_m": -20, "altitude_m": 15},
        {"north_m": 10, "east_m": -20, "altitude_m": 15},
        {"north_m": 10, "east_m": 20, "altitude_m": 15},
    ]


def test_generate_lawnmower_spacing_larger_than_field_still_covers_edges():
    waypoints = survey.generate_lawnmower(
        width_m=10,
        height_m=5,
        spacing_m=50,
        altitude_m=10,
    )

    assert waypoints == [
        {"north_m": -2.5, "east_m": -5, "altitude_m": 10},
        {"north_m": -2.5, "east_m": 5, "altitude_m": 10},
        {"north_m": 2.5, "east_m": 5, "altitude_m": 10},
        {"north_m": 2.5, "east_m": -5, "altitude_m": 10},
    ]


def test_generate_lawnmower_minimal_one_by_one_pattern():
    waypoints = survey.generate_lawnmower(
        width_m=1,
        height_m=1,
        spacing_m=2,
        altitude_m=1,
    )

    assert waypoints == [
        {"north_m": -0.5, "east_m": -0.5, "altitude_m": 1},
        {"north_m": -0.5, "east_m": 0.5, "altitude_m": 1},
        {"north_m": 0.5, "east_m": 0.5, "altitude_m": 1},
        {"north_m": 0.5, "east_m": -0.5, "altitude_m": 1},
    ]


@pytest.mark.parametrize(
    ("width_m", "height_m", "spacing_m", "altitude_m"),
    [
        (0, 10, 5, 10),
        (10, 0, 5, 10),
        (10, 10, 0, 10),
        (10, 10, 5, 0),
    ],
)
def test_generate_lawnmower_rejects_non_positive_inputs(
    width_m,
    height_m,
    spacing_m,
    altitude_m,
):
    with pytest.raises(ValueError):
        survey.generate_lawnmower(width_m, height_m, spacing_m, altitude_m)


def test_validate_survey_waypoints_rejects_out_of_geofence_pattern():
    waypoints = survey.generate_lawnmower(
        width_m=500,
        height_m=20,
        spacing_m=10,
        altitude_m=15,
    )

    result = survey.validate_survey_waypoints(waypoints)

    assert result["ok"] is False
    assert result["refused"] is True
    assert result["waypoint_index"] == 0
    assert "GEOFENCE_RADIUS_M=200" in result["reason"]


def test_validate_survey_waypoints_rejects_excessive_altitude():
    waypoints = survey.generate_lawnmower(
        width_m=20,
        height_m=20,
        spacing_m=10,
        altitude_m=100,
    )

    result = survey.validate_survey_waypoints(waypoints, safety.SafetyLimits())

    assert result["ok"] is False
    assert result["refused"] is True
    assert "MAX_ALT_M=50" in result["reason"]


def test_validate_survey_waypoints_accepts_safe_pattern():
    waypoints = survey.generate_lawnmower(40, 30, 10, 15)

    result = survey.validate_survey_waypoints(waypoints)

    assert result == {"ok": True, "refused": False, "num_waypoints": len(waypoints)}
