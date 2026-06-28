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
        "Call list_log_topics first to see what was recorded, get_log_summary "
        "for an overview, query_topic for bounded signal samples, "
        "get_failsafe_events for arming and failsafe transitions, and "
        "diagnose_flight for an opinionated health verdict. Pass absolute file "
        "paths."
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


@mcp.tool
def query_topic(
    path: str,
    topic: str,
    fields: list[str] | str | None = None,
    start_s: float | None = None,
    end_s: float | None = None,
    multi_id: int = 0,
    max_samples: int = 500,
) -> dict:
    """Query fields from one uORB topic over a seconds-from-log-start window.

    Call `list_log_topics` first to discover topic and field names. `path` must
    be an absolute path to a .ulg file. `fields` may be omitted to return every
    non-timestamp field, a single field name, or a list of field names. `start_s`
    and `end_s` are seconds from log start. Large result sets are automatically
    decimated to `max_samples`, while stats still cover the full filtered window.
    """
    return ulog_tools.query_topic(
        path=path,
        topic=topic,
        fields=fields,
        start_s=start_s,
        end_s=end_s,
        multi_id=multi_id,
        max_samples=max_samples,
    )


@mcp.tool
def get_failsafe_events(path: str) -> dict:
    """Extract arming and failsafe-related events from a PX4 ULog file.

    `path` must be an absolute path to a .ulg file. Returns chronological
    vehicle_status changes such as arming-state transitions, failsafe flags,
    RC/data-link loss, engine or mission failure flags, failsafe navigation
    modes, and derived armed intervals.
    """
    return ulog_tools.get_failsafe_events(path)


@mcp.tool
def diagnose_flight(path: str) -> dict:
    """Run an opinionated health check over a PX4 ULog file.

    `path` must be an absolute path to a .ulg file. Bundles the common
    "what went wrong" heuristics — logged errors, EKF innovation divergence and
    fault flags, vibration, CPU load, low battery, failsafe events, and flight-
    mode thrash — into a single `healthy` verdict with a list of `findings`
    (each with a severity and supporting evidence). Checks whose topics are not
    in the log are reported under `checks_skipped` rather than failing the call.
    Best single call for "is this flight healthy and, if not, why?".
    """
    return ulog_tools.diagnose_flight(path)


def main() -> None:
    """Console-script entry point. Defaults to stdio transport."""
    mcp.run()


if __name__ == "__main__":
    main()
