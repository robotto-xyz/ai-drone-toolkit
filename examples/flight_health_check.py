"""Quick "did anything go wrong?" check for a PX4 flight log.

Builds on robotto-drone-core's `get_log_summary` to surface the two things you
usually care about first: the flight-mode timeline and any logged warnings or
errors. Exits non-zero when warnings/errors are present, so it doubles as a
simple CI / batch gate over a directory of logs.

Run from the repository root:

    uv run python examples/flight_health_check.py /absolute/path/to/flight.ulg

With no argument it falls back to the PX4 sample fixture (download it first
with `cd packages/robotto-drone-core && make sample-log`).
"""

from __future__ import annotations

import sys
from pathlib import Path

from robotto_drone_core import ulog_tools

DEFAULT_SAMPLE = (
    Path(__file__).resolve().parents[1]
    / "packages"
    / "robotto-drone-core"
    / "tests"
    / "sample.ulg"
)


def main(argv: list[str]) -> int:
    log_path = (
        Path(argv[1]).expanduser().resolve() if len(argv) > 1 else DEFAULT_SAMPLE
    )
    if not log_path.is_file():
        print(f"Log file not found: {log_path}\n")
        print("Pass a path to a .ulg file, or download the sample fixture:")
        print("  cd packages/robotto-drone-core && make sample-log")
        return 2

    try:
        summary = ulog_tools.get_log_summary(str(log_path))
    except ulog_tools.ULogError as exc:
        print(f"Failed to read log: {exc}")
        return 2

    print(f"Flight: {summary['file']}  ({summary['duration_s']} s)")

    modes = summary["flight_modes"]
    print(f"\nFlight-mode timeline ({len(modes)} changes):")
    if modes:
        for change in modes:
            print(f"  t={change['t_s']:>8.3f}s  {change['mode']}")
    else:
        print("  (no vehicle_status logged)")

    issues = summary["warnings_and_errors"]
    print(f"\nWarnings/errors: {summary['num_warnings_or_errors']}")
    for issue in issues:
        print(f"  t={issue['t_s']:>8.3f}s  [{issue['level']}] {issue['message']}")

    if issues:
        print("\nResult: issues found.")
        return 1
    print("\nResult: clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
