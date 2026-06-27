# PX4 SITL Commander — MCP Server

Simulation-only [Model Context Protocol](https://modelcontextprotocol.io) server
for commanding a PX4 drone in SITL. It lets an AI assistant compose safe verbs
like "connect to the sim, take off to 15 meters, fly 50 meters north, then land"
into structured tool calls.

This tool is deliberately **not** for real hardware. Every command path is
guarded by the shared safety layer in
[`robotto-drone-core`](../../packages/robotto-drone-core): local-SITL-only
connection gate, altitude limit, geofence, speed cap, arming preconditions, and
structured refusals an LLM can relay.

## Tools

| Tool | What it does | Safety checks |
|------|--------------|---------------|
| `connect_sim(address)` | Connect to local PX4 SITL and wait for healthy global/home position. | Local UDP SITL endpoint only. |
| `get_drone_state()` | Read armed status, flight mode, position, relative altitude, and battery. | Read-only. |
| `takeoff(altitude_m)` | Arm and take off promptly to a relative altitude above home. | Simulation gate, arming preconditions, `MAX_ALT_M`. |
| `land()` | Land at the current position. | Requires the simulated drone to be armed. |
| `goto(north_m, east_m, altitude_m)` | Fly to a meters-from-home offset and wait until reached. | Simulation gate, geofence, `MAX_ALT_M`, AMSL conversion. |

## Install

This tool lives at `tools/px4-sitl-mcp` inside the
[AI Drone Toolkit](../../README.md) uv workspace.

```bash
git clone https://github.com/robotto-xyz/ai-drone-toolkit.git
cd ai-drone-toolkit
uv sync --all-packages
```

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/). The MAVSDK
dependency is isolated to this tool so other toolkit members do not drag it in.

## Start PX4 SITL

This server does not start PX4 for you. Run SITL separately, then connect to its
local MAVSDK endpoint. One common path:

```bash
cd /path/to/PX4-Autopilot
make px4_sitl gz_x500
```

If Gazebo is troublesome on your machine, use a headless/jMAVSim/Docker SITL
setup that exposes a local UDP endpoint compatible with MAVSDK. The default
address expected by this server is:

```text
udpin://0.0.0.0:14540
```

The simulation-only gate refuses non-UDP, non-localhost, or wrong-port
addresses.

## Run the server

```bash
uv run px4-sitl-mcp
```

The server speaks stdio, so MCP clients launch it as a subprocess.

### Cursor — `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (global)

```json
{
  "mcpServers": {
    "px4-sitl": {
      "command": "uv",
      "args": ["run", "px4-sitl-mcp"]
    }
  }
}
```

If your MCP client launches from another working directory, point `uv` at this
workspace explicitly:

```json
{
  "mcpServers": {
    "px4-sitl": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/ai-drone-toolkit", "run", "px4-sitl-mcp"]
    }
  }
}
```

## Good first prompts

> Connect to the sim, get the drone state, take off to 15 meters, then land.

> Try to take off to 1000 meters and explain the safety refusal.

The second prompt should return a structured refusal from the core safety layer
before MAVSDK receives any command.

## Coordinate and altitude conventions

The LLM-facing `goto` tool accepts intuitive meters-from-home offsets:

- `north_m`: meters north of home.
- `east_m`: meters east of home.
- `altitude_m`: relative altitude above home in meters.

Internally, the tool converts north/east offsets to latitude/longitude and
converts relative altitude to absolute AMSL altitude because MAVSDK
`goto_location` expects AMSL. PX4 local frame landmines (NED vs ENU, down is
positive) are handled in `robotto_drone_core.frames`.

## Examples

The following scripts require a running PX4 SITL instance:

```bash
uv run python examples/sitl_connect_state.py
uv run python examples/sitl_takeoff_land.py
uv run python examples/sitl_fly_path.py
```

They are intentionally documented as live-SITL examples. Unit tests cover the
pure safety and conversion logic without a simulator; flight behavior must be
verified by running PX4 SITL locally.

## Test

Run simulator-free tests:

```bash
uv run pytest tools/px4-sitl-mcp packages/robotto-drone-core
```

Run the whole workspace:

```bash
uv run pytest
```

## License

MIT.
