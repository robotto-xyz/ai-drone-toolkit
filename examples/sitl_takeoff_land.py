"""Take off and land in PX4 SITL through px4-sitl-mcp's drone layer.

Requires a running PX4 SITL instance exposing the default MAVSDK endpoint
(`udpin://0.0.0.0:14540`). This is a live simulator example; it is not exercised
by the default test suite.

Run from the repository root:

    uv run python examples/sitl_takeoff_land.py
"""

from __future__ import annotations

import asyncio
import json

from px4_sitl_mcp.drone import drone


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

        await asyncio.sleep(3)

        land = await drone.land()
        print("land:")
        print(json.dumps(land, indent=2))
        return 0 if land.get("ok") else 1
    finally:
        drone.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
