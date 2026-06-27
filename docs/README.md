# Documentation

Documentation for the **AI Drone Toolkit** — a [uv](https://docs.astral.sh/uv/)
workspace monorepo of packages and tools for working with drone flight data and
bringing AI assistants closer to the robotics stack.

## What lives in this repo

| Path | Description |
|------|-------------|
| [`packages/robotto-drone-core`](../packages/robotto-drone-core) | Shared, MCP-agnostic parsers and utilities. Hosts the PX4 ULog parsing layer used across the toolkit. |
| [`tools/px4-ulog-mcp`](../tools/px4-ulog-mcp) | [Model Context Protocol](https://modelcontextprotocol.io) server that exposes PX4 ULog (`.ulg`) inspection as structured tools. A thin MCP layer over the core. |
| [`examples/`](../examples) | Runnable scripts showing how to use the core package directly. |
| [`docs/`](.) | Project-wide documentation (you are here). |

## Architecture in one line

Shared logic lives in `robotto-drone-core`; each tool (e.g. `px4-ulog-mcp`) is a
thin, independently usable layer on top of it. The same parsing code can back an
MCP server, a CLI, an example script, or a web app without duplication.

## Getting started

This project uses [uv](https://docs.astral.sh/uv/) and targets Python 3.12+.

```bash
git clone https://github.com/robotto-xyz/ai-drone-toolkit.git
cd ai-drone-toolkit
uv sync --all-packages
```

`uv sync --all-packages` builds every workspace member into a single shared
virtual environment. Each package/tool also has its own `README.md` with
specifics — see the relevant subdirectory.

## Documentation index

This directory is the home for project-wide documentation. As the toolkit
grows, add focused guides here, for example:

- `architecture.md` — how the packages and tools fit together in depth.
- `contributing.md` — development workflow, testing, and conventions.
- Per-tool deep dives that go beyond a tool's own `README.md`.

For usage today, see:

- [`packages/robotto-drone-core/README.md`](../packages/robotto-drone-core/README.md)
  — the shared parsing API.
- [`tools/px4-ulog-mcp/README.md`](../tools/px4-ulog-mcp/README.md) — install,
  wire into your editor, and analyze PX4 flight logs.

## Examples

Looking for runnable code? Head to the [`examples/`](../examples) directory —
`analyze_ulog.py` and `flight_health_check.py` both drive the core parsing layer.
