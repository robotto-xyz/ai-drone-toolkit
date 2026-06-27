# Examples

Runnable examples for the **AI Drone Toolkit**. Each one is a small,
self-contained demonstration of how to use the toolkit's packages — primarily
the shared [`robotto-drone-core`](../packages/robotto-drone-core) package and
the MCP tool layers.

## Prerequisites

This project is a [uv](https://docs.astral.sh/uv/) workspace targeting Python
3.12+. From the repository root, set up the workspace once:

```bash
uv sync --all-packages
```

The ULog examples default to the PX4 sample log used by the test suite.
Download it once (or pass your own `.ulg` path as the first argument):

```bash
cd packages/robotto-drone-core && make sample-log && cd -
```

## Running an example

Run examples through the workspace `uv` environment so they pick up the local
workspace packages and their dependencies:

```bash
uv run python examples/<example_name>.py [path/to/flight.ulg]
```

## Available examples

| Example | What it shows |
|---------|---------------|
| [`analyze_ulog.py`](analyze_ulog.py) | Parse a `.ulg` log with `robotto_drone_core.ulog_tools` and print a flight summary plus the busiest recorded topics. |
| [`flight_health_check.py`](flight_health_check.py) | Surface the flight-mode timeline and any logged warnings/errors, exiting non-zero when issues are found — handy as a batch/CI gate. |
| [`sitl_connect_state.py`](sitl_connect_state.py) | Connect to a running PX4 SITL instance and print read-only drone state. Requires live SITL. |
| [`sitl_takeoff_land.py`](sitl_takeoff_land.py) | Connect, take off to 15 m, wait briefly, and land. Requires live SITL. |
| [`sitl_fly_path.py`](sitl_fly_path.py) | Fly a small multi-waypoint meters-from-home path through `goto`, then land. Requires live SITL. |

```bash
# Summarize the sample log (or your own):
uv run python examples/analyze_ulog.py
uv run python examples/analyze_ulog.py /absolute/path/to/flight.ulg

# Flag anything that looks wrong:
uv run python examples/flight_health_check.py

# PX4 SITL examples (start SITL first):
uv run python examples/sitl_connect_state.py
uv run python examples/sitl_takeoff_land.py
uv run python examples/sitl_fly_path.py
```

## PX4 SITL examples

The `sitl_*` examples are live simulator examples. Start PX4 SITL separately
before running them, for example:

```bash
cd /path/to/PX4-Autopilot
make px4_sitl gz_x500
```

They use the default local MAVSDK endpoint `udpin://0.0.0.0:14540`. The
simulation-only safety gate refuses non-localhost or wrong-port addresses.

## Contributing an example

When adding a new example:

1. Keep it small and focused on a single concept.
2. Add a module docstring at the top explaining what it demonstrates and how to
   run it.
3. List it in the **Available examples** table above.

See the [`docs/`](../docs) directory for broader project documentation.
