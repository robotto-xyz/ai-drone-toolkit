"""Thin, LLM-friendly wrappers around pyulog.

This module deliberately knows nothing about MCP. It takes file paths and
returns plain dicts/lists of JSON-serializable primitives. That separation
makes the logic unit-testable without spinning up a server, and lets you
reuse it from a CLI, a web app, or any MCP server in the toolkit.
"""

from __future__ import annotations

import math
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

# PX4 arming_state enum -> human label. Unknown values are surfaced explicitly.
ARMING_STATE_NAMES = {
    0: "INIT",
    1: "STANDBY",
    2: "ARMED",
    3: "STANDBY_ERROR",
    4: "SHUTDOWN",
    5: "IN_AIR_RESTORE",
}

FAILSAFE_BOOL_FIELDS = (
    "failsafe",
    "rc_signal_lost",
    "data_link_lost",
    "engine_failure",
    "mission_failure",
)

FAILSAFE_NAV_STATES = {
    5: "AUTO_RTL",
    12: "DESCEND",
    13: "TERMINATION",
    18: "AUTO_LAND",
}

# diagnose_flight heuristic thresholds. Tunable; grounded in PX4 log-review
# conventions (EKF innovation test ratios reject at 1.0; vibration and CPU
# bands follow the PX4 flight-review guidance).
EKF_TEST_RATIO_WARN = 0.5
EKF_TEST_RATIO_CRIT = 1.0
VIBE_WARN_MS = 30.0
VIBE_CRIT_MS = 60.0
CPU_LOAD_WARN = 0.90
CPU_LOAD_CRIT = 0.95
BATTERY_REMAINING_WARN = 0.20
BATTERY_REMAINING_CRIT = 0.10
MODE_CHANGES_WARN = 12

# EKF innovation test-ratio fields (>1.0 == measurement rejected).
EKF_TEST_RATIO_FIELDS = (
    "vel_test_ratio",
    "pos_test_ratio",
    "hgt_test_ratio",
    "mag_test_ratio",
)

# Severity ordering for sorting findings worst-first.
_SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}


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


def _label(mapping: dict[int, str], value: Any) -> str:
    value_i = int(value)
    return mapping.get(value_i, f"UNKNOWN({value_i})")


def _to_primitive(value: Any) -> Any:
    """Convert numpy/pyulog scalars into JSON-serializable Python primitives."""
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    if isinstance(value, (list, tuple)):
        return [_to_primitive(v) for v in value]
    return value


def _numeric_value(value: Any) -> float | None:
    value = _to_primitive(value)
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        value_f = float(value)
        if math.isfinite(value_f):
            return value_f
    return None


def _field_stats(values: list[Any]) -> dict[str, Any]:
    numeric = [v for v in (_numeric_value(value) for value in values) if v is not None]
    stats: dict[str, Any] = {
        "first": _to_primitive(values[0]) if values else None,
        "last": _to_primitive(values[-1]) if values else None,
    }
    if numeric:
        stats.update(
            {
                "min": min(numeric),
                "max": max(numeric),
                "mean": round(sum(numeric) / len(numeric), 6),
            }
        )
    return stats


def _available_topics(ulog: ULog) -> str:
    topics = sorted({d.name for d in ulog.data_list})
    return ", ".join(topics[:20]) + ("..." if len(topics) > 20 else "")


def _dataset_field_stats(
    ulog: ULog, topic: str, field: str, multi_id: int = 0
) -> dict[str, Any] | None:
    """Full-series stats for one topic field, or ``None`` if it isn't logged.

    Used by :func:`diagnose_flight` so each heuristic can degrade gracefully
    when a topic or field is missing instead of raising.
    """
    try:
        dataset = ulog.get_dataset(topic, multi_id)
    except (KeyError, IndexError):
        return None
    if field not in dataset.data:
        return None
    return _field_stats(list(dataset.data[field]))


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


def query_topic(
    path: str,
    topic: str,
    fields: list[str] | str | None = None,
    start_s: float | None = None,
    end_s: float | None = None,
    multi_id: int = 0,
    max_samples: int = 500,
) -> dict[str, Any]:
    """Pull selected signal fields from one uORB topic over a time window.

    Samples are returned as seconds from log start and decimated when needed so
    LLM-facing payloads stay bounded. Per-field stats cover the full filtered
    window, not just the returned samples.
    """
    if max_samples <= 0:
        raise ULogError("max_samples must be greater than 0")
    if start_s is not None and end_s is not None and start_s > end_s:
        raise ULogError("start_s must be less than or equal to end_s")

    ulog = _safe_load(path)
    try:
        dataset = ulog.get_dataset(topic, multi_id)
    except (KeyError, IndexError) as exc:
        raise ULogError(
            f"Topic not found: {topic} multi_id={multi_id}. "
            f"Available topics include: {_available_topics(ulog)}"
        ) from exc

    timestamps = dataset.data.get("timestamp")
    if timestamps is None:
        raise ULogError(f"Topic {topic} does not contain a timestamp field")

    available_fields = sorted(k for k in dataset.data.keys() if k != "timestamp")
    if fields is None:
        selected_fields = available_fields
    elif isinstance(fields, str):
        selected_fields = [fields]
    else:
        selected_fields = list(fields)

    invalid_fields = [field for field in selected_fields if field not in dataset.data]
    if invalid_fields:
        raise ULogError(
            f"Field(s) not found for topic {topic}: {', '.join(invalid_fields)}. "
            f"Available fields: {', '.join(available_fields)}"
        )

    indices: list[int] = []
    for i, timestamp in enumerate(timestamps):
        t_s = _rel_s(timestamp, ulog.start_timestamp)
        if start_s is not None and t_s < start_s:
            continue
        if end_s is not None and t_s > end_s:
            continue
        indices.append(i)

    stride = 1
    returned_indices = indices
    if len(indices) > max_samples:
        stride = math.ceil(len(indices) / max_samples)
        returned_indices = indices[::stride]

    samples = []
    for i in returned_indices:
        sample = {"t_s": _rel_s(timestamps[i], ulog.start_timestamp)}
        for field in selected_fields:
            sample[field] = _to_primitive(dataset.data[field][i])
        samples.append(sample)

    stats = {
        field: _field_stats([dataset.data[field][i] for i in indices])
        for field in selected_fields
    }

    return {
        "file": os.path.basename(path),
        "topic": topic,
        "multi_id": int(multi_id),
        "fields": selected_fields,
        "start_s": start_s,
        "end_s": end_s,
        "num_samples_total": len(indices),
        "num_samples_returned": len(samples),
        "decimated": len(indices) > len(samples),
        "decimation_stride": stride,
        "stats": stats,
        "samples": samples,
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


def _failsafe_events(ulog: ULog) -> dict[str, Any] | None:
    """Build failsafe/arming events from a loaded log.

    Returns ``None`` when the log has no ``vehicle_status`` topic so callers can
    decide how to surface the gap. Shared by :func:`get_failsafe_events` and
    :func:`diagnose_flight` so the parse happens once per call site.
    """
    try:
        vs = ulog.get_dataset("vehicle_status")
    except (KeyError, IndexError):
        return None

    events: list[dict[str, Any]] = []

    arming_changes: list[tuple[float, int]] = []
    if "arming_state" in vs.data:
        previous: int | None = None
        for timestamp, value in vs.list_value_changes("arming_state"):
            current = int(value)
            t_s = _rel_s(timestamp, ulog.start_timestamp)
            arming_changes.append((t_s, current))
            events.append(
                {
                    "t_s": t_s,
                    "type": "arming_state",
                    "field": "arming_state",
                    "from": _label(ARMING_STATE_NAMES, previous) if previous is not None else None,
                    "to": _label(ARMING_STATE_NAMES, current),
                    "detail": f"arming_state changed to {_label(ARMING_STATE_NAMES, current)}",
                }
            )
            previous = current

    for field in FAILSAFE_BOOL_FIELDS:
        if field not in vs.data:
            continue
        previous_bool: bool | None = None
        for timestamp, value in vs.list_value_changes(field):
            current_bool = bool(value)
            events.append(
                {
                    "t_s": _rel_s(timestamp, ulog.start_timestamp),
                    "type": field,
                    "field": field,
                    "from": previous_bool,
                    "to": current_bool,
                    "detail": f"{field} {'set' if current_bool else 'cleared'}",
                }
            )
            previous_bool = current_bool

    if "nav_state" in vs.data:
        previous_nav: int | None = None
        for timestamp, value in vs.list_value_changes("nav_state"):
            current_nav = int(value)
            if current_nav in FAILSAFE_NAV_STATES:
                events.append(
                    {
                        "t_s": _rel_s(timestamp, ulog.start_timestamp),
                        "type": "failsafe_nav_state",
                        "field": "nav_state",
                        "from": _label(NAV_STATE_NAMES, previous_nav) if previous_nav is not None else None,
                        "to": _label(NAV_STATE_NAMES, current_nav),
                        "detail": f"navigation switched to {_label(NAV_STATE_NAMES, current_nav)}",
                    }
                )
            previous_nav = current_nav

    armed_intervals = []
    armed_start_s: float | None = None
    for t_s, state in arming_changes:
        if state == 2 and armed_start_s is None:
            armed_start_s = t_s
        elif state != 2 and armed_start_s is not None:
            armed_intervals.append(
                {
                    "start_s": armed_start_s,
                    "end_s": t_s,
                    "duration_s": round(t_s - armed_start_s, 3),
                }
            )
            armed_start_s = None
    if armed_start_s is not None:
        armed_intervals.append(
            {
                "start_s": armed_start_s,
                "end_s": None,
                "duration_s": None,
            }
        )

    events.sort(key=lambda event: event["t_s"])
    return {
        "events": events,
        "armed_intervals": armed_intervals,
    }


def get_failsafe_events(path: str) -> dict[str, Any]:
    """Extract arming, failsafe, and failsafe-like navigation transitions."""
    ulog = _safe_load(path, ["vehicle_status"])
    data = _failsafe_events(ulog)
    if data is None:
        return {
            "file": os.path.basename(path),
            "num_events": 0,
            "events": [],
            "armed_intervals": [],
            "note": "vehicle_status topic not present in this log",
        }
    return {
        "file": os.path.basename(path),
        "num_events": len(data["events"]),
        "events": data["events"],
        "armed_intervals": data["armed_intervals"],
    }


def _finding(
    check: str, severity: str, detail: str, evidence: dict[str, Any] | None = None
) -> dict[str, Any]:
    finding: dict[str, Any] = {"check": check, "severity": severity, "detail": detail}
    if evidence is not None:
        finding["evidence"] = evidence
    return finding


def _in_any_interval(t_s: float, intervals: list[dict[str, Any]]) -> bool:
    for interval in intervals:
        start = interval.get("start_s")
        end = interval.get("end_s")
        if start is None:
            continue
        if end is None:
            if t_s >= start:
                return True
        elif start <= t_s <= end:
            return True
    return False


def diagnose_flight(path: str) -> dict[str, Any]:
    """Opinionated "what went wrong" bundle for a PX4 ULog file.

    Composes the same primitives the other tools expose (logged messages, signal
    stats, failsafe events) into a single health verdict an LLM can relay. Each
    heuristic degrades gracefully: a check whose topic isn't in the log is
    reported under ``checks_skipped`` instead of failing the whole call.

    Returns ``healthy`` plus a list of ``findings`` (each with a severity and the
    evidence behind it). Thresholds live in module constants and are tunable.
    """
    ulog = _safe_load(path)
    duration_s = round((ulog.last_timestamp - ulog.start_timestamp) / 1e6, 3)

    findings: list[dict[str, Any]] = []
    checks_run: list[str] = []
    checks_skipped: list[dict[str, str]] = []

    # 1. Logged messages: ERR and above are smoking guns; WARNING is a heads-up.
    checks_run.append("logged_errors")
    severe: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for m in ulog.logged_messages:
        lvl = _log_level_name(m.log_level)
        entry = {"t_s": _rel_s(m.timestamp, ulog.start_timestamp), "level": lvl, "message": m.message}
        if lvl in ("EMERG", "ALERT", "CRIT", "ERR"):
            severe.append(entry)
        elif lvl == "WARNING":
            warnings.append(entry)
    if severe:
        findings.append(
            _finding(
                "logged_errors",
                "critical",
                f"{len(severe)} error-level message(s) logged during the flight",
                {"count": len(severe), "samples": severe[:5]},
            )
        )
    if warnings:
        findings.append(
            _finding(
                "logged_errors",
                "warning",
                f"{len(warnings)} warning-level message(s) logged during the flight",
                {"count": len(warnings), "samples": warnings[:5]},
            )
        )

    # 2. EKF innovation test ratios (>1.0 == measurement rejected / divergence).
    worst_ratio: float | None = None
    worst_field: str | None = None
    for field in EKF_TEST_RATIO_FIELDS:
        stats = _dataset_field_stats(ulog, "estimator_status", field)
        if stats is None or "max" not in stats:
            continue
        if worst_ratio is None or stats["max"] > worst_ratio:
            worst_ratio = stats["max"]
            worst_field = field
    if worst_ratio is not None:
        checks_run.append("ekf_innovations")
        if worst_ratio >= EKF_TEST_RATIO_CRIT:
            findings.append(
                _finding(
                    "ekf_innovations",
                    "critical",
                    f"EKF innovation {worst_field}={worst_ratio:.2f} exceeded {EKF_TEST_RATIO_CRIT} (estimator rejecting measurements)",
                    {"field": worst_field, "max": worst_ratio},
                )
            )
        elif worst_ratio >= EKF_TEST_RATIO_WARN:
            findings.append(
                _finding(
                    "ekf_innovations",
                    "warning",
                    f"EKF innovation {worst_field}={worst_ratio:.2f} elevated (>{EKF_TEST_RATIO_WARN})",
                    {"field": worst_field, "max": worst_ratio},
                )
            )
    else:
        checks_skipped.append(
            {"check": "ekf_innovations", "reason": "estimator_status test ratios not in log"}
        )

    # 3. EKF fault / NaN flags (any non-zero bit is a hard fault).
    fault_stats = _dataset_field_stats(ulog, "estimator_status", "filter_fault_flags")
    nan_stats = _dataset_field_stats(ulog, "estimator_status", "nan_flags")
    if fault_stats is not None or nan_stats is not None:
        checks_run.append("ekf_faults")
        fault_max = int(fault_stats["max"]) if fault_stats and "max" in fault_stats else 0
        nan_max = int(nan_stats["max"]) if nan_stats and "max" in nan_stats else 0
        if fault_max or nan_max:
            findings.append(
                _finding(
                    "ekf_faults",
                    "critical",
                    f"EKF reported fault flags (filter_fault_flags={fault_max}, nan_flags={nan_max})",
                    {"filter_fault_flags": fault_max, "nan_flags": nan_max},
                )
            )
    else:
        checks_skipped.append(
            {"check": "ekf_faults", "reason": "estimator_status fault flags not in log"}
        )

    # 4. Vibration (high-frequency delta-velocity, estimator_status.vibe[2]).
    vibe_stats = _dataset_field_stats(ulog, "estimator_status", "vibe[2]")
    if vibe_stats is not None and "max" in vibe_stats:
        checks_run.append("vibration")
        vibe_max = vibe_stats["max"]
        if vibe_max >= VIBE_CRIT_MS:
            findings.append(
                _finding(
                    "vibration",
                    "critical",
                    f"Peak vibration {vibe_max:.1f} m/s exceeded {VIBE_CRIT_MS} m/s",
                    {"max": vibe_max},
                )
            )
        elif vibe_max >= VIBE_WARN_MS:
            findings.append(
                _finding(
                    "vibration",
                    "warning",
                    f"Peak vibration {vibe_max:.1f} m/s above the {VIBE_WARN_MS} m/s caution band",
                    {"max": vibe_max},
                )
            )
    else:
        checks_skipped.append({"check": "vibration", "reason": "estimator_status vibe not in log"})

    # 5. CPU load.
    cpu_stats = _dataset_field_stats(ulog, "cpuload", "load")
    if cpu_stats is not None and "max" in cpu_stats:
        checks_run.append("cpu_load")
        cpu_max = cpu_stats["max"]
        if cpu_max >= CPU_LOAD_CRIT:
            findings.append(
                _finding(
                    "cpu_load",
                    "critical",
                    f"Peak CPU load {cpu_max * 100:.0f}% exceeded {CPU_LOAD_CRIT * 100:.0f}%",
                    {"max": cpu_max},
                )
            )
        elif cpu_max >= CPU_LOAD_WARN:
            findings.append(
                _finding(
                    "cpu_load",
                    "warning",
                    f"Peak CPU load {cpu_max * 100:.0f}% above {CPU_LOAD_WARN * 100:.0f}%",
                    {"max": cpu_max},
                )
            )
    else:
        checks_skipped.append({"check": "cpu_load", "reason": "cpuload topic not in log"})

    # 6. Battery (remaining is a 0..1 fraction).
    battery_stats = _dataset_field_stats(ulog, "battery_status", "remaining")
    if battery_stats is not None and "min" in battery_stats:
        checks_run.append("battery")
        remaining_min = battery_stats["min"]
        if remaining_min <= BATTERY_REMAINING_CRIT:
            findings.append(
                _finding(
                    "battery",
                    "critical",
                    f"Battery dropped to {remaining_min * 100:.0f}% (<= {BATTERY_REMAINING_CRIT * 100:.0f}%)",
                    {"min_remaining": remaining_min},
                )
            )
        elif remaining_min <= BATTERY_REMAINING_WARN:
            findings.append(
                _finding(
                    "battery",
                    "warning",
                    f"Battery dropped to {remaining_min * 100:.0f}% (<= {BATTERY_REMAINING_WARN * 100:.0f}%)",
                    {"min_remaining": remaining_min},
                )
            )
    else:
        checks_skipped.append({"check": "battery", "reason": "battery_status topic not in log"})

    # 7. Failsafe / arming events.
    failsafe = _failsafe_events(ulog)
    if failsafe is None:
        checks_skipped.append({"check": "failsafe", "reason": "vehicle_status topic not in log"})
    else:
        checks_run.append("failsafe")
        armed_intervals = failsafe["armed_intervals"]
        for event in failsafe["events"]:
            etype = event["type"]
            if etype in ("failsafe", "engine_failure", "mission_failure") and event["to"] is True:
                findings.append(
                    _finding(
                        "failsafe",
                        "critical",
                        event["detail"],
                        {"t_s": event["t_s"], "type": etype},
                    )
                )
            elif etype == "failsafe_nav_state" and event["to"] in ("DESCEND", "TERMINATION"):
                findings.append(
                    _finding(
                        "failsafe",
                        "critical",
                        event["detail"],
                        {"t_s": event["t_s"], "to": event["to"]},
                    )
                )
            elif (
                etype in ("rc_signal_lost", "data_link_lost")
                and event["to"] is True
                and _in_any_interval(event["t_s"], armed_intervals)
            ):
                findings.append(
                    _finding(
                        "failsafe",
                        "warning",
                        f"{etype} while armed",
                        {"t_s": event["t_s"], "type": etype},
                    )
                )

    # 8. Mode thrash (excessive nav_state switching).
    try:
        vs = ulog.get_dataset("vehicle_status")
    except (KeyError, IndexError):
        vs = None
    if vs is not None and "nav_state" in vs.data:
        checks_run.append("mode_thrash")
        num_changes = len(vs.list_value_changes("nav_state"))
        if num_changes > MODE_CHANGES_WARN:
            findings.append(
                _finding(
                    "mode_thrash",
                    "warning",
                    f"{num_changes} flight-mode changes (>{MODE_CHANGES_WARN}) suggest mode thrash",
                    {"num_changes": num_changes},
                )
            )
    else:
        checks_skipped.append({"check": "mode_thrash", "reason": "vehicle_status nav_state not in log"})

    findings.sort(key=lambda f: (_SEVERITY_RANK.get(f["severity"], 9), f["check"]))
    healthy = not findings
    return {
        "file": os.path.basename(path),
        "duration_s": duration_s,
        "healthy": healthy,
        "verdict": "nominal" if healthy else "issues_found",
        "num_findings": len(findings),
        "findings": findings,
        "checks_run": checks_run,
        "checks_skipped": checks_skipped,
    }
