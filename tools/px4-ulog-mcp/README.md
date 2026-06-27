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

Both take an **absolute path** to a `.ulg` file.

## Install

This tool lives at `tools/px4-ulog-mcp` inside the
[AI Drone Toolkit](../../README.md) uv workspace. Clone the toolkit and sync
once from its root:

```bash
git clone https://github.com/robotto-xyz/ai-drone-toolkit.git
cd ai-drone-toolkit
uv sync
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
```

Run this from the repository root. If your Python session is started from
another directory, pass an absolute path to the `.ulg` file instead.

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

## Where to take it next

This is a deliberately small v1. Natural follow-on tools:

- `query_topic(path, topic, start_s, end_s)` — pull a single signal over a time
  window (battery voltage, altitude, EKF innovations) for fine-grained analysis.
- `get_failsafe_events(path)` — extract failsafe triggers and arming state changes.
- `diagnose_flight(path)` — bundle the common "what went wrong" heuristics
  (EKF divergence, low battery, high vibration) into one opinionated call.

The parsing logic lives in `robotto_drone_core.ulog_tools` and is independent of
MCP, so each new tool is a small function in the shared core package plus a thin
`@mcp.tool` wrapper in `server.py`.

## License

MIT.
