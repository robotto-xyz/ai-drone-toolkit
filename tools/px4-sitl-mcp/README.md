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
| `connect_sim(address)` | Connect to local PX4 SITL, wait for healthy global/home position, and apply the speed cap. | Local UDP SITL endpoint only, `MAX_SPEED_MS` pushed to PX4 via `set_current_speed`. |
| `get_drone_state()` | Read armed status, flight mode, position, relative altitude, and battery. | Read-only. |
| `takeoff(altitude_m)` | Arm and take off promptly to a relative altitude above home. | Simulation gate, arming preconditions, `MAX_ALT_M`. |
| `land()` | Land at the current position. | Requires the simulated drone to be armed. |
| `goto(north_m, east_m, altitude_m)` | Fly to a meters-from-home offset and wait until reached. | Simulation gate, geofence, `MAX_ALT_M`, AMSL conversion. |
| `fly_survey_pattern(width_m, height_m, spacing_m, altitude_m)` | Fly a centered lawnmower survey and return home. | Validates every waypoint against geofence and altitude before flying any of them. |
| `connect_drone(drone_id, address)` | Connect one named local PX4 SITL drone. | Per-drone simulation gate. |
| `connect_drones(count)` | Connect 1-3 local SITL drones using documented default addresses. | Per-drone simulation gate. |
| `list_drones()` | List known drone ids and local connection bookkeeping. | Read-only. |
| `command_drone(drone_id, action, ...)` | Dispatch an existing single-drone action to one named drone. | Same safety checks as the underlying action. |

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

## Multi-instance PX4 SITL

Multi-drone support in this tool is intentionally scoped to proving that
multiple local SITL connections can be managed safely. It is **not** swarm
behavior, formation control, collision avoidance, or a higher-level autonomy
stack.

PX4 multi-instance startup varies by local setup. A typical PX4-Autopilot
workflow uses instance-specific startup scripts and distinct MAVSDK UDP ports.
One common pattern is:

```bash
cd /path/to/PX4-Autopilot

# Terminal 1
PX4_SYS_AUTOSTART=4001 PX4_SIM_MODEL=gz_x500 ./build/px4_sitl_default/bin/px4 -i 1

# Terminal 2
PX4_SYS_AUTOSTART=4001 PX4_SIM_MODEL=gz_x500 ./build/px4_sitl_default/bin/px4 -i 2
```

Depending on your PX4/Gazebo version, you may instead use PX4's documented
multi-vehicle Gazebo targets or helper scripts. The important constraints for
this MCP server are:

- Each simulated drone must expose a **local UDP** MAVSDK endpoint.
- Each endpoint must use a distinct local port.
- Each endpoint is checked independently by the simulation-only safety gate.

This repository's default convenience mapping is:

| Drone id | Default address |
|----------|-----------------|
| `drone-1` | `udpin://0.0.0.0:14540` |
| `drone-2` | `udpin://0.0.0.0:14541` |
| `drone-3` | `udpin://0.0.0.0:14542` |

The single-drone tools (`connect_sim`, `takeoff`, `goto`, `land`,
`fly_survey_pattern`) and the fleet tools share **one** namespace: `drone-1` is
the fleet default, i.e. the same vehicle the single-drone tools operate on.
There is no separate hidden `default` drone pointed at the same `14540`
endpoint. `connect_drones(n)` connects `drone-1 … drone-n`.

Live multi-instance behavior is not verified by the automated test suite; run
it locally with multiple PX4 SITL instances before claiming demo readiness.

### Design questions for the founders

The current multi-drone layer proves connection management and per-drone safety
only. These are intentionally **not** implemented until the founders' real stack
and command semantics are understood:

- Command granularity: should tools command individual drones, teams, or a
  swarm-level objective?
- Swarm-level intent: who decomposes "search this area" into routes, altitudes,
  and deconfliction?
- Collision avoidance: is it handled by PX4, a separate autonomy layer, or a
  centralized coordinator?
- Real-stack mapping: does the founders' swarm stack expose ROS 2 actions,
  MAVSDK-like vehicle handles, mission APIs, or something else?
- Security/audit: what authentication, authorization, and command logging should
  exist before a swarm-level interface is exposed?

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

> Survey a 40 by 30 meter area at 15 meters altitude, then come home.

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

`goto` polls telemetry until the target is reached within a settling tolerance
(`GOTO_HORIZONTAL_TOLERANCE_M`, default 4 m; `GOTO_VERTICAL_TOLERANCE_M`,
default 1.5 m, in `config.py`). PX4's onboard position controller parks a few
meters from the commanded point rather than exactly on it, so a tighter
tolerance would report false timeouts on waypoints the drone actually hit.

`takeoff` is treated as complete once the drone climbs to within
`TAKEOFF_REACH_TOLERANCE_M` (default 1 m) *below* the commanded altitude. PX4's
auto-takeoff settles slightly **above** the requested altitude (observed holding
~16.5 m for a 15 m command), so an exact-match check would never trigger; this
overshoot is expected and counts as success.

## Survey pattern

`fly_survey_pattern(width_m, height_m, spacing_m, altitude_m)` generates a
centered lawnmower path around home:

- `width_m`: east/west span in meters.
- `height_m`: north/south span in meters.
- `spacing_m`: distance between passes in meters.
- `altitude_m`: relative altitude above home in meters.

The generator lives in `robotto_drone_core.survey` and returns plain
meters-from-home waypoints. Before the drone moves, the tool validates **every**
waypoint against the geofence and altitude limits. If any waypoint is unsafe,
the whole survey is refused up front; it never flies halfway through a pattern
and then refuses.

## Examples

The following scripts require a running PX4 SITL instance:

```bash
uv run python examples/sitl_connect_state.py
uv run python examples/sitl_takeoff_land.py
uv run python examples/sitl_fly_path.py
uv run python examples/sitl_fly_survey.py
uv run python examples/sitl_multi_drone.py
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
