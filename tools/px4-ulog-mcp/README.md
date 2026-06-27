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

```bash
git clone https://github.com/robotto-xyz/px4-ulog-mcp.git
cd px4-ulog-mcp
uv sync
```

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

## Test

Grab a sample log and run the test suite:

```bash
make check
```

This downloads `tests/sample.ulg` and runs `pytest` through the project `uv`
environment. After the sample log exists, rerun tests with:

```bash
make test
```

Avoid running bare `pytest`; it can pick up unrelated global plugins from your
machine.

## Try it

You can also smoke-test the parsing layer with no MCP client:

```python
from pathlib import Path
from px4_ulog_mcp import ulog_tools

log_path = Path("tests/sample.ulg").resolve()
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
      "args": ["--directory", "/absolute/path/to/px4-ulog-mcp", "run", "px4-ulog-mcp"]
    }
  }
}
```

### Claude Code

```bash
claude mcp add px4-ulog -- uv --directory /absolute/path/to/px4-ulog-mcp run px4-ulog-mcp
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

The parsing logic lives in `ulog_tools.py` and is independent of MCP, so each new
tool is a small function there plus a thin `@mcp.tool` wrapper in `server.py`.

## License

MIT.
