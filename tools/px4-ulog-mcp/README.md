# PX4 ULog Analyzer — MCP Server

A tiny [Model Context Protocol](https://modelcontextprotocol.io) server that lets
an AI assistant (Cursor, Claude Code, Claude Desktop, etc.) inspect PX4 flight
logs (`.ulg`) through structured tools instead of guesswork.

Ask your assistant *"what's in this log?"* or *"did anything go wrong on this
flight?"* and it calls real tools that parse the log with
[`pyulog`](https://github.com/PX4/pyulog).

## Tools

| Tool | What it does |
|------|--------------|
| `list_log_topics(path)` | Inventory of recorded uORB topics: name, multi-id, sample count, fields. The cheap "what's in here" call. |
| `get_log_summary(path)` | Duration, hardware/firmware, flight-mode timeline, dropouts, and all logged warnings/errors. The "what happened" call. |
| `query_topic(path, topic, fields, start_s, end_s, multi_id, max_samples)` | Pull bounded samples and stats for one topic over a seconds-from-log-start window. Use it for battery, altitude, EKF, and other signal checks. |
| `get_failsafe_events(path)` | Extract arming-state changes, failsafe flags, RC/data-link loss, engine/mission failure flags, failsafe nav modes, and armed intervals. |
| `diagnose_flight(path)` | Opinionated health verdict: logged errors, EKF innovation/fault flags, vibration, CPU load, low battery, failsafe events, and mode thrash, with a `healthy` flag and severity-ranked findings. |

All tools take an **absolute path** to a `.ulg` file.

## Install

This tool lives at `tools/px4-ulog-mcp` inside the
[AI Drone Toolkit](../../README.md) uv workspace. Clone the toolkit and sync
once from its root:

```bash
git clone https://github.com/robotto-xyz/ai-drone-toolkit.git
cd ai-drone-toolkit
uv sync --all-packages
```

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/). The flight-log
parsing itself lives in the shared
[`robotto-drone-core`](../../packages/robotto-drone-core) package; this tool is
the thin MCP layer on top of it.

## Test

The parsing logic — and its test suite — live in `robotto-drone-core`. Run
them from that package:

```bash
cd packages/robotto-drone-core
make check
```

This downloads `tests/sample.ulg` and runs `pytest` through the workspace `uv`
environment. After the sample log exists, rerun tests with `make test`.

## Try it

You can smoke-test the parsing layer directly, with no MCP client:

```python
from pathlib import Path
from robotto_drone_core import ulog_tools

log_path = Path("packages/robotto-drone-core/tests/sample.ulg").resolve()
print(ulog_tools.get_log_summary(str(log_path)))
print(
    ulog_tools.query_topic(
        str(log_path),
        topic="vehicle_local_position",
        fields=["z"],
        start_s=10,
        end_s=12,
        max_samples=20,
    )
)
print(ulog_tools.get_failsafe_events(str(log_path)))
print(ulog_tools.diagnose_flight(str(log_path)))
```

Run this from the repository root. If your Python session is started from
another directory, pass an absolute path to the `.ulg` file instead.

For ready-made scripts, see the toolkit's
[`examples/`](../../examples) directory (`analyze_ulog.py`,
`flight_health_check.py`).

## Wire it into your editor

The server speaks **stdio**, so any MCP client launches it as a subprocess.

### Cursor — `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (global)

```json
{
  "mcpServers": {
    "px4-ulog": {
      "command": "uv",
      "args": ["run", "px4-ulog-mcp"]
    }
  }
}
```

If your MCP client launches from a different working directory, point `uv` at
this project explicitly:

```json
{
  "mcpServers": {
    "px4-ulog": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/ai-drone-toolkit", "run", "px4-ulog-mcp"]
    }
  }
}
```

### Claude Code

```bash
claude mcp add px4-ulog -- uv --directory /absolute/path/to/ai-drone-toolkit run px4-ulog-mcp
```

or add the same block to `.mcp.json` in your project root.

### Claude Desktop — `claude_desktop_config.json`

Same `mcpServers` block as Cursor above. Restart the app, then look for the
tools in the connector list.

## A good first prompt

> I have a flight log at `/Users/me/logs/crash.ulg`. List its topics, then give
> me a summary and tell me whether anything looks wrong.

The assistant should call `list_log_topics`, then `get_log_summary`, and reason
over the errors and flight-mode timeline it gets back.

For deeper follow-up, ask for a specific signal or safety timeline:

> Query altitude from 10 to 30 seconds and summarize the min/max/mean.

> Show me arming and failsafe events with timestamps.

> Diagnose this flight and tell me if anything looks unhealthy.

## Where to take it next

The four tools above cover discovery, overview, signal queries, failsafe
timelines, and an opinionated health verdict. Natural follow-on work:

- Tune `diagnose_flight` thresholds against more real logs and add GPS-accuracy
  and actuator-saturation heuristics.
- A short demo recording of the analyzer answering "what went wrong?" end to end.

The parsing logic lives in `robotto_drone_core.ulog_tools` and is independent of
MCP, so each new tool is a small function in the shared core package plus a thin
`@mcp.tool` wrapper in `server.py`.

## License

MIT.
