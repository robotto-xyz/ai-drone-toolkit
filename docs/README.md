# Documentation

Documentation for the **AI Drone Toolkit** — a monorepo of packages and tools
for working with drone flight data and bringing AI assistants closer to the
robotics stack.

## What lives in this repo

| Path | Description |
|------|-------------|
| `packages/robotto-drone-core` | Core library with shared drone data models and utilities. |
| `tools/px4-ulog-mcp` | [Model Context Protocol](https://modelcontextprotocol.io) server for inspecting PX4 ULog (`.ulg`) flight logs through structured tools. |
| `examples/` | Runnable examples showing how to use the packages and tools. |

## Getting started

This project uses [uv](https://docs.astral.sh/uv/) and targets Python 3.12+.

```bash
git clone https://github.com/robotto-xyz/ai-drone-toolkit.git
cd ai-drone-toolkit
uv sync
```

Each tool and package may have its own `pyproject.toml` and setup steps — see
the `README.md` in the relevant subdirectory for details.

## Documentation index

This directory is the home for project-wide documentation. As the toolkit
grows, add focused guides here, for example:

- `architecture.md` — how the packages and tools fit together.
- `contributing.md` — development workflow, testing, and conventions.
- Per-tool deep dives that go beyond the tool's own `README.md`.

For tool-specific usage today, see:

- [`tools/px4-ulog-mcp/README.md`](../tools/px4-ulog-mcp/README.md) — install,
  wire into your editor, and analyze PX4 flight logs.

## Examples

Looking for runnable code? Head to the [`examples/`](../examples) directory.
