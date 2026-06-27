# Examples

Runnable examples for the **AI Drone Toolkit**. Each one is a small,
self-contained demonstration of how to use the toolkit's packages — primarily
the shared [`robotto-drone-core`](../packages/robotto-drone-core) parsing layer.

## Prerequisites

This project is a [uv](https://docs.astral.sh/uv/) workspace targeting Python
3.12+. From the repository root, set up the workspace once:

```bash
uv sync --all-packages
```

The examples default to the PX4 sample log used by the test suite. Download it
once (or pass your own `.ulg` path as the first argument):

```bash
cd packages/robotto-drone-core && make sample-log && cd -
```

## Running an example

Run examples through the workspace `uv` environment so they pick up
`robotto-drone-core` and its dependencies:

```bash
uv run python examples/<example_name>.py [path/to/flight.ulg]
```

## Available examples

| Example | What it shows |
|---------|---------------|
| [`analyze_ulog.py`](analyze_ulog.py) | Parse a `.ulg` log with `robotto_drone_core.ulog_tools` and print a flight summary plus the busiest recorded topics. |
| [`flight_health_check.py`](flight_health_check.py) | Surface the flight-mode timeline and any logged warnings/errors, exiting non-zero when issues are found — handy as a batch/CI gate. |

```bash
# Summarize the sample log (or your own):
uv run python examples/analyze_ulog.py
uv run python examples/analyze_ulog.py /absolute/path/to/flight.ulg

# Flag anything that looks wrong:
uv run python examples/flight_health_check.py
```

## Contributing an example

When adding a new example:

1. Keep it small and focused on a single concept.
2. Add a module docstring at the top explaining what it demonstrates and how to
   run it.
3. List it in the **Available examples** table above.

See the [`docs/`](../docs) directory for broader project documentation.
