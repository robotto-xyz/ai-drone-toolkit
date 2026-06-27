# Examples

Runnable examples for the **AI Drone Toolkit**. Each example is meant to be a
small, self-contained demonstration of how to use the packages and tools in
this repo.

## Prerequisites

This project uses [uv](https://docs.astral.sh/uv/) and targets Python 3.12+.
From the repository root:

```bash
uv sync
```

## Running an example

Run examples through the project's `uv` environment so they pick up the right
dependencies:

```bash
uv run python examples/<example_name>.py
```

## Available examples

_No examples yet._ This directory is the home for runnable samples as the
toolkit grows. Good candidates to add:

- **Analyze a PX4 flight log** — call the parsing layer from
  [`px4-ulog-mcp`](../tools/px4-ulog-mcp) directly to summarize a `.ulg` file
  without an MCP client.
- **Use `robotto-drone-core`** — a minimal script showing the core data models
  and utilities in action.

## Contributing an example

When adding a new example:

1. Keep it small and focused on a single concept.
2. Add a short comment at the top explaining what it demonstrates and how to
   run it.
3. List it under **Available examples** above.

See the [`docs/`](../docs) directory for broader project documentation.
