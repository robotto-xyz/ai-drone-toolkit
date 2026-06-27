"""PX4 ULog Analyzer — MCP server.

Exposes PX4 flight-log (.ulg) inspection as MCP tools so an AI assistant in
Cursor / Claude Code can answer questions like "what's in this log?" or
"did anything go wrong on this flight?" by calling structured tools instead
of guessing.

Run locally over stdio (default):
    python -m px4_ulog_mcp.server
or via the installed console script:
    px4-ulog-mcp
"""

from __future__ import annotations

from fastmcp import FastMCP
from robotto_drone_core import ulog_tools

mcp = FastMCP(
    name="px4-ulog-analyzer",
    instructions=(
        "Tools for inspecting PX4 ULog (.ulg) flight logs. "
        "Call list_log_topics first to see what was recorded, then "
        "get_log_summary for an overview of duration, flight modes, and any "
        "errors. Pass absolute file paths."
    ),
)


@mcp.tool
def list_log_topics(path: str) -> dict:
    """List the uORB topics recorded in a PX4 ULog file.

    Returns each topic's name, multi-instance id, sample count, and field
    names. Use this first to discover what data a log contains before
    requesting details. `path` must be an absolute path to a .ulg file.
    """
    return ulog_tools.list_log_topics(path)


@mcp.tool
def get_log_summary(path: str) -> dict:
    """Summarize a PX4 ULog flight: duration, hardware/firmware, flight-mode
    timeline, dropouts, and any logged warnings or errors.

    This is the best single call for "what kind of flight was this and did
    anything obviously go wrong?". `path` must be an absolute path to a .ulg
    file.
    """
    return ulog_tools.get_log_summary(path)


def main() -> None:
    """Console-script entry point. Defaults to stdio transport."""
    mcp.run()


if __name__ == "__main__":
    main()
