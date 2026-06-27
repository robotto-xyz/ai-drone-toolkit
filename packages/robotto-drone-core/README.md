# robotto-drone-core

Shared parsers, utilities, and data models for the
[AI Drone Toolkit](../../README.md). This package is **MCP-agnostic**: it takes
file paths and returns plain, JSON-friendly dicts/lists so the same logic can
back an MCP server, a CLI, or a web app without duplication.

## What's here

| Module | Description |
|--------|-------------|
| `robotto_drone_core.ulog_tools` | Parse PX4 ULog (`.ulg`) flight logs: list recorded uORB topics and build a high-level flight summary (duration, hardware/firmware, flight-mode timeline, dropouts, warnings/errors). |

## Usage

```python
from pathlib import Path
from robotto_drone_core import ulog_tools

log_path = Path("flight.ulg").resolve()
print(ulog_tools.list_log_topics(str(log_path)))
print(ulog_tools.get_log_summary(str(log_path)))
```

## Develop

This package is a member of the toolkit's uv workspace. From the repository
root run `uv sync` once, then work on it like any other member.

Run the parsing tests (downloads the official PX4 sample log first):

```bash
make check
```

After the sample log exists, rerun tests with `make test`.

## License

MIT.
