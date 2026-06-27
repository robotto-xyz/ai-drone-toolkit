<p align="center">
  <img src="docs/assets/banner.jpg" alt="AI Drone Toolkit by Robotto" width="100%" />
</p>

# AI Drone Toolkit

MCP servers and tools for intelligent drone development (PX4 and beyond). The
toolkit gives AI assistants (Cursor, Claude, etc.) structured tools to
understand, debug, and reason about drone systems — starting with PX4 flight
logs.

This is a [uv](https://docs.astral.sh/uv/) workspace monorepo: shared logic
lives in a core package, and each tool is a thin, independently usable layer on
top of it.

## Repository layout

| Path | Description |
|------|-------------|
| [`packages/robotto-drone-core`](packages/robotto-drone-core) | Shared, MCP-agnostic parsers and utilities (PX4 ULog parsing today). |
| [`tools/px4-ulog-mcp`](tools/px4-ulog-mcp) | MCP server for inspecting PX4 ULog (`.ulg`) flight logs. |
| [`docs/`](docs) | Project-wide documentation. |
| [`examples/`](examples) | Runnable examples and demos. |

## Getting started

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/robotto-xyz/ai-drone-toolkit.git
cd ai-drone-toolkit
uv sync --all-packages
```

This sets up a single virtual environment for the whole workspace. From there,
work on any member, e.g. run the PX4 ULog MCP server:

```bash
uv run px4-ulog-mcp
```

## Documentation

- [`docs/`](docs) — architecture and project-wide guides.
- [`tools/px4-ulog-mcp/README.md`](tools/px4-ulog-mcp/README.md) — install,
  wire into your editor, and analyze flight logs.

## License

MIT.
