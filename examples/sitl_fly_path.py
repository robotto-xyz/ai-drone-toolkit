"""Fly a small multi-waypoint path in PX4 SITL.

Requires a running PX4 SITL instance exposing the default MAVSDK endpoint
(`udpin://0.0.0.0:14540`). This is a live simulator example; it is not exercised
by the default test suite.

Run from the repository root:

    uv run python examples/sitl_fly_path.py
"""

from __future__ import annotations

import asyncio
import json

from px4_sitl_mcp.drone import drone

WAYPOINTS = [
    (20.0, 0.0, 15.0),
    (20.0, 20.0, 15.0),
    (0.0, 20.0, 15.0),
    (0.0, 0.0, 15.0),
]


async def main() -> int:
    try:
        connect = await drone.connect()
        print("connect:")
        print(json.dumps(connect, indent=2))
        if not connect.get("ok"):
            return 1

        takeoff = await drone.takeoff(15)
        print("takeoff:")
        print(json.dumps(takeoff, indent=2))
        if not takeoff.get("ok"):
            return 1

        for north_m, east_m, altitude_m in WAYPOINTS:
            result = await drone.goto(north_m, east_m, altitude_m)
            print(f"goto north={north_m} east={east_m} altitude={altitude_m}:")
            print(json.dumps(result, indent=2))
            if not result.get("ok"):
                return 1

        land = await drone.land()
        print("land:")
        print(json.dumps(land, indent=2))
        return 0 if land.get("ok") else 1
    finally:
        drone.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
