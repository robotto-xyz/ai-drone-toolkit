# robotto-drone-core

Shared parsers, utilities, and data models for the
[AI Drone Toolkit](../../README.md). This package is **MCP-agnostic**: it takes
file paths and returns plain, JSON-friendly dicts/lists so the same logic can
back an MCP server, a CLI, or a web app without duplication.

## What's here

| Module | Description |
|--------|-------------|
| `robotto_drone_core.ulog_tools` | Parse PX4 ULog (`.ulg`) flight logs: list recorded uORB topics and build a high-level flight summary (duration, hardware/firmware, flight-mode timeline, dropouts, warnings/errors). |
| `robotto_drone_core.safety` | Pure safety checks for simulation-only drone command tools: local SITL gate, altitude limit, geofence, speed cap, arming preconditions, and structured refusals. |
| `robotto_drone_core.frames` | Coordinate-frame and altitude helpers: NED/ENU conversion, relative/AMSL altitude conversion, meters-from-home to lat/lon, and target-reached checks. |

## Usage

```python
from pathlib import Path
from robotto_drone_core import ulog_tools

log_path = Path("flight.ulg").resolve()
print(ulog_tools.list_log_topics(str(log_path)))
print(ulog_tools.get_log_summary(str(log_path)))
```

## Safety model

Commanding real aircraft is out of scope for this repository. Reusable safety
logic lives here in the core so it can be unit-tested without an MCP server,
MAVSDK, PX4 SITL, or hardware.

Defaults:

| Limit | Default | Why it exists |
|-------|---------|---------------|
| `SIMULATION_ONLY` | `True` | Refuse any non-localhost/non-SITL MAVSDK address before commands can arm. |
| `MAX_ALT_M` | `50 m` | Prevent LLM-generated commands such as "take off to 5000 meters" from reaching PX4. |
| `GEOFENCE_RADIUS_M` | `200 m` | Keep `goto` targets inside a bounded meters-from-home radius. |
| `MAX_SPEED_MS` | `10 m/s` | Bound commanded speed before it reaches MAVSDK. |
| Arming preconditions | global position + home position healthy | Surface clear refusals before PX4 returns a lower-level command denial. |

Safety functions return JSON-serializable results that an LLM can relay:

```python
from robotto_drone_core import safety

result = safety.clamp_altitude(5000)
print(result)
# {
#   "ok": False,
#   "refused": True,
#   "reason": "Requested 5000 m exceeds MAX_ALT_M=50",
#   ...
# }
```

Coordinate helpers keep the command tools explicit about domain landmines:
PX4's local frame is NED (down is positive), while MAVSDK `goto_location` uses
absolute AMSL altitude rather than relative height above home.

## Develop

This package is a member of the toolkit's uv workspace. From the repository
root run `uv sync --all-packages` once, then work on it like any other member.

Run the full core test suite:

```bash
uv run pytest packages/robotto-drone-core
```

The ULog parsing tests use the official PX4 sample log. Download it first when
you want those fixture-backed assertions to run:

```bash
make check
```

After the sample log exists, rerun tests with `make test`.

## See it in action

- [`tools/px4-ulog-mcp`](../../tools/px4-ulog-mcp) — wraps this package as an
  MCP server.
- [`tools/px4-sitl-mcp`](../../tools/px4-sitl-mcp) — uses the safety and frame
  helpers before sending any command to PX4 SITL.
- [`examples/analyze_ulog.py`](../../examples/analyze_ulog.py) and
  [`examples/flight_health_check.py`](../../examples/flight_health_check.py) —
  drive `ulog_tools` directly.

## License

MIT.
