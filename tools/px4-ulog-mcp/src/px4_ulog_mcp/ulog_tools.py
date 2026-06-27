"""Thin, LLM-friendly wrappers around pyulog.

This module deliberately knows nothing about MCP. It takes file paths and
returns plain dicts/lists of JSON-serializable primitives. That separation
makes the logic unit-testable without spinning up a server, and lets you
reuse it from a CLI, a web app, or the MCP server in server.py.
"""

from __future__ import annotations

import os
from typing import Any

from pyulog import ULog

# PX4 nav_state enum -> human label. Trimmed to the common ones; extend freely.
# Source: PX4 vehicle_status.msg nav_state definitions.
NAV_STATE_NAMES = {
    0: "MANUAL",
    1: "ALTCTL",
    2: "POSCTL",
    3: "AUTO_MISSION",
    4: "AUTO_LOITER",
    5: "AUTO_RTL",
    10: "ACRO",
    12: "DESCEND",
    13: "TERMINATION",
    14: "OFFBOARD",
    15: "STAB",
    17: "AUTO_TAKEOFF",
    18: "AUTO_LAND",
    20: "AUTO_PRECLAND",
}

# pyulog log_level is a syslog-style severity byte (the ASCII digit).
LOG_LEVEL_NAMES = {
    0: "EMERG", 1: "ALERT", 2: "CRIT", 3: "ERR",
    4: "WARNING", 5: "NOTICE", 6: "INFO", 7: "DEBUG",
}


class ULogError(Exception):
    """Raised for any problem loading or reading a ULog file."""


def _rel_s(t: Any, start: Any) -> float:
    """Seconds since log start, computed in Python ints to dodge numpy
    unsigned-int underflow when a change is timestamped at/just before start."""
    return round((int(t) - int(start)) / 1e6, 3)


def _safe_load(path: str, message_filter: list[str] | None = None) -> ULog:
    """Load a ULog with friendly errors and string-exception tolerance.

    ``disable_str_exceptions=True`` keeps a single corrupt string message from
    aborting the whole parse — common in real-world crash logs.
    """
    if not os.path.isfile(path):
        raise ULogError(f"File not found: {path}")
    if not path.lower().endswith((".ulg", ".ulog")):
        raise ULogError(f"Not a ULog file (expected .ulg): {path}")
    try:
        return ULog(path, message_filter, True)
    except Exception as exc:  # pyulog raises bare Exceptions in places
        raise ULogError(f"Failed to parse {path}: {exc}") from exc


def _log_level_name(level: Any) -> str:
    """Map pyulog's log_level to a severity name.

    pyulog exposes log_level as the raw syslog byte, which is the ASCII
    character of the digit (e.g. 51 == ord('3') == ERR), not the integer 3.
    Handle both forms defensively.
    """
    try:
        lvl = int(level)
    except (TypeError, ValueError):
        return str(level)
    if lvl in LOG_LEVEL_NAMES:           # already an integer severity
        return LOG_LEVEL_NAMES[lvl]
    if 48 <= lvl <= 57:                  # ASCII '0'..'9'
        return LOG_LEVEL_NAMES.get(lvl - 48, str(lvl - 48))
    return str(lvl)


def list_log_topics(path: str) -> dict[str, Any]:
    """Inventory of logged uORB topics: name, multi-instance id, sample count.

    This is the cheap 'what's in this log' call an agent should make first,
    before deciding which topics are worth pulling in detail.
    """
    ulog = _safe_load(path)
    topics = []
    for d in ulog.data_list:
        # Every dataset has a timestamp field; len of it == number of samples.
        n = len(d.data.get("timestamp", []))
        topics.append(
            {
                "name": d.name,
                "multi_id": d.multi_id,
                "num_samples": int(n),
                "fields": sorted(k for k in d.data.keys() if k != "timestamp"),
            }
        )
    topics.sort(key=lambda t: t["name"])
    return {
        "file": os.path.basename(path),
        "num_topics": len(topics),
        "topics": topics,
    }


def get_log_summary(path: str) -> dict[str, Any]:
    """High-level overview: duration, hardware/software, flight modes, errors.

    Designed to be the single call that gives an LLM enough context to reason
    about 'what kind of flight was this and did anything obviously go wrong'.
    """
    ulog = _safe_load(path)

    duration_s = (ulog.last_timestamp - ulog.start_timestamp) / 1e6

    info = ulog.msg_info_dict
    sw = info.get("ver_sw", "unknown")

    # Flight-mode timeline from vehicle_status.nav_state, if present.
    flight_modes: list[dict[str, Any]] = []
    try:
        vs = ulog.get_dataset("vehicle_status")
        for t, nav in vs.list_value_changes("nav_state"):
            flight_modes.append(
                {
                    "t_s": _rel_s(t, ulog.start_timestamp),
                    "nav_state": int(nav),
                    "mode": NAV_STATE_NAMES.get(int(nav), f"UNKNOWN({int(nav)})"),
                }
            )
    except (KeyError, IndexError):
        pass  # not all logs contain vehicle_status

    # Logged printf messages, bucketed by severity. ERR/CRIT are the smoking guns.
    errors = []
    for m in ulog.logged_messages:
        lvl = _log_level_name(m.log_level)
        if lvl in ("EMERG", "ALERT", "CRIT", "ERR", "WARNING"):
            errors.append(
                {
                    "t_s": _rel_s(m.timestamp, ulog.start_timestamp),
                    "level": lvl,
                    "message": m.message,
                }
            )

    return {
        "file": os.path.basename(path),
        "duration_s": round(duration_s, 3),
        "sys_name": info.get("sys_name", "unknown"),
        "hardware": info.get("ver_hw", "unknown"),
        "sw_version": sw,
        "dropouts": len(ulog.dropouts),
        "num_topics": len(ulog.data_list),
        "num_params": len(ulog.initial_parameters),
        "flight_modes": flight_modes,
        "num_warnings_or_errors": len(errors),
        "warnings_and_errors": errors,
    }
