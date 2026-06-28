"""Connect to two PX4 SITL drones and command each independently.

Requires two running PX4 SITL instances exposing local MAVSDK endpoints:

    drone-1: udpin://0.0.0.0:14540
    drone-2: udpin://0.0.0.0:14541

This is a live multi-simulator example; it is not exercised by the default test
suite and does not implement swarm behavior.

Run from the repository root:

    uv run python examples/sitl_multi_drone.py
"""

from __future__ import annotations

import asyncio
import json

from px4_sitl_mcp.drone import fleet


async def main() -> int:
    try:
        connect = await fleet.connect_drones(2)
        print("connect_drones:")
        print(json.dumps(connect, indent=2))
        if not connect.get("ok"):
            return 1

        first = await fleet.command_drone("drone-1", "takeoff", altitude_m=10)
        print("drone-1 takeoff:")
        print(json.dumps(first, indent=2))
        if not first.get("ok"):
            return 1

        second = await fleet.command_drone("drone-2", "takeoff", altitude_m=12)
        print("drone-2 takeoff:")
        print(json.dumps(second, indent=2))
        if not second.get("ok"):
            return 1

        await asyncio.sleep(3)

        for drone_id in ("drone-1", "drone-2"):
            land = await fleet.command_drone(drone_id, "land")
            print(f"{drone_id} land:")
            print(json.dumps(land, indent=2))
            if not land.get("ok"):
                return 1

        return 0
    finally:
        fleet.close_all()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
