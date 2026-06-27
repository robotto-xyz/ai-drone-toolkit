"""PX4 SITL Commander — MCP server.

Exposes simulation-only PX4 command tools over stdio. The tools are thin
wrappers around ``px4_sitl_mcp.drone`` and reusable safety/frame logic in
``robotto_drone_core``.
"""

from __future__ import annotations

from fastmcp import FastMCP

from . import config
from .drone import drone, fleet

mcp = FastMCP(
    name="px4-sitl-commander",
    instructions=(
        "Simulation-only tools for commanding a PX4 SITL drone on localhost. "
        "Always connect with connect_sim first, inspect state with "
        "get_drone_state, and respect structured refusals from the safety "
        "layer. Coordinates for goto are meters-from-home: north/east offsets "
        "and relative altitude in meters. Survey patterns validate the entire "
        "path before flying. Never use these tools for real hardware."
    ),
)


async def _guard_tool(call) -> dict:
    try:
        return await call()
    except Exception as exc:  # keep raw tracebacks out of MCP tool results
        return {
            "ok": False,
            "refused": False,
            "reason": f"px4-sitl-mcp tool failed: {exc}",
        }


@mcp.tool
async def connect_sim(address: str = config.DEFAULT_SIM_ADDRESS) -> dict:
    """Connect to a local PX4 SITL instance and wait until it is ready.

    `address` must be a localhost UDP SITL endpoint such as
    `udpin://0.0.0.0:14540`. Non-localhost or non-SITL addresses are refused by
    the simulation-only safety gate. This also waits for PX4 to report healthy
    global and home position before returning ready.
    """

    return await _guard_tool(lambda: drone.connect(address))


@mcp.tool
async def get_drone_state() -> dict:
    """Return current read-only state for the connected PX4 SITL drone.

    The result includes armed status, flight mode, latitude/longitude, absolute
    AMSL altitude, relative altitude above home, and battery percentage. This is
    read-only but still connects to local SITL if needed.
    """

    return await _guard_tool(drone.get_state)


@mcp.tool
async def takeoff(altitude_m: float) -> dict:
    """Arm and take off promptly to a relative altitude in meters.

    `altitude_m` is height above home, not AMSL. The shared safety layer refuses
    non-positive or excessive altitudes (default MAX_ALT_M=50). This tool arms
    and starts takeoff in one call to avoid PX4's auto-disarm window, then polls
    telemetry before reporting completion.
    """

    return await _guard_tool(lambda: drone.takeoff(altitude_m))


@mcp.tool
async def land() -> dict:
    """Land the connected PX4 SITL drone at its current position."""

    return await _guard_tool(drone.land)


@mcp.tool
async def goto(north_m: float, east_m: float, altitude_m: float) -> dict:
    """Fly to a meters-from-home target and wait until it is reached.

    `north_m` and `east_m` are local offsets from the home position in meters.
    `altitude_m` is relative altitude above home in meters, not AMSL. The shared
    safety layer enforces the geofence and altitude limit before MAVSDK receives
    the command; internally this tool converts the target to latitude,
    longitude, and AMSL altitude for MAVSDK `goto_location`.
    """

    return await _guard_tool(lambda: drone.goto(north_m, east_m, altitude_m))


@mcp.tool
async def fly_survey_pattern(
    width_m: float,
    height_m: float,
    spacing_m: float,
    altitude_m: float,
) -> dict:
    """Fly a centered lawnmower survey pattern in PX4 SITL.

    `width_m` spans east/west, `height_m` spans north/south, `spacing_m` is the
    distance between passes, and `altitude_m` is relative altitude above home.
    The generated waypoints use meters-from-home coordinates. The entire pattern
    is validated against altitude and geofence limits before any waypoint is
    flown; if any waypoint is unsafe, the whole pattern is refused up front.
    """

    return await _guard_tool(
        lambda: drone.fly_survey_pattern(width_m, height_m, spacing_m, altitude_m)
    )


@mcp.tool
async def connect_drone(drone_id: str, address: str) -> dict:
    """Connect one named local PX4 SITL drone.

    Each `address` is independently validated by the simulation-only gate and
    must be a local UDP SITL endpoint. This proves multi-connection plumbing; it
    does not create swarm-level behavior.
    """

    return await _guard_tool(lambda: fleet.connect_drone(drone_id, address))


@mcp.tool
async def connect_drones(count: int) -> dict:
    """Connect `count` local PX4 SITL drones using documented default addresses.

    Defaults are `drone-1` -> port 14540, `drone-2` -> 14541, and `drone-3` ->
    14542. Use `connect_drone` for explicit addresses if your PX4 setup differs.
    """

    return await _guard_tool(lambda: fleet.connect_drones(count))


@mcp.tool
async def list_drones() -> dict:
    """List known simulated drones and local connection bookkeeping.

    This is read-only and does not contact PX4. Use `get_drone_state` or
    `command_drone(..., action="get_state")` to read live telemetry.
    """

    return fleet.list_drones()


@mcp.tool
async def command_drone(
    drone_id: str,
    action: str,
    altitude_m: float | None = None,
    north_m: float | None = None,
    east_m: float | None = None,
    width_m: float | None = None,
    height_m: float | None = None,
    spacing_m: float | None = None,
) -> dict:
    """Issue one existing single-drone action to a named simulated drone.

    Supported actions are `get_state`, `takeoff`, `goto`, `land`, and
    `fly_survey_pattern`. This is intentionally per-drone command plumbing, not
    formation control, collision avoidance, or swarm-level intent.
    """

    return await _guard_tool(
        lambda: fleet.command_drone(
            drone_id,
            action,
            altitude_m=altitude_m,
            north_m=north_m,
            east_m=east_m,
            width_m=width_m,
            height_m=height_m,
            spacing_m=spacing_m,
        )
    )


def main() -> None:
    """Console-script entry point. Defaults to stdio transport."""

    mcp.run()


if __name__ == "__main__":
    main()
