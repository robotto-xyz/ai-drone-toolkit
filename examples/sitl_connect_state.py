"""Connect to PX4 SITL and print read-only state.

Requires a running PX4 SITL instance exposing the default MAVSDK endpoint
(`udpin://0.0.0.0:14540`). This is a live simulator example; it is not exercised
by the default test suite.

Run from the repository root:

    uv run python examples/sitl_connect_state.py
"""

from __future__ import annotations

import asyncio
import json

from px4_sitl_mcp.drone import drone


async def main() -> int:
    state = await drone.get_state()
    print(json.dumps(state, indent=2))
    return 0 if state.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
