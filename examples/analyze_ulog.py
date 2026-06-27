"""Analyze a PX4 ULog file with robotto-drone-core.

Demonstrates the shared parsing layer directly — no MCP client required. It
prints a topic inventory and a high-level flight summary for a `.ulg` file.

Run from the repository root:

    # Use your own log:
    uv run python examples/analyze_ulog.py /absolute/path/to/flight.ulg

    # Or fall back to the PX4 sample fixture (download it first with
    # `cd packages/robotto-drone-core && make sample-log`):
    uv run python examples/analyze_ulog.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from robotto_drone_core import ulog_tools

# The core package ships a Makefile target that downloads this sample log.
DEFAULT_SAMPLE = (
    Path(__file__).resolve().parents[1]
    / "packages"
    / "robotto-drone-core"
    / "tests"
    / "sample.ulg"
)


def resolve_log_path(argv: list[str]) -> Path:
    if len(argv) > 1:
        return Path(argv[1]).expanduser().resolve()
    return DEFAULT_SAMPLE


def main(argv: list[str]) -> int:
    log_path = resolve_log_path(argv)
    if not log_path.is_file():
        print(f"Log file not found: {log_path}\n")
        print("Pass a path to a .ulg file, or download the sample fixture:")
        print("  cd packages/robotto-drone-core && make sample-log")
        return 1

    try:
        topics = ulog_tools.list_log_topics(str(log_path))
        summary = ulog_tools.get_log_summary(str(log_path))
    except ulog_tools.ULogError as exc:
        print(f"Failed to read log: {exc}")
        return 1

    print(f"File: {summary['file']}")
    print(f"Hardware: {summary['hardware']}  |  SW: {summary['sw_version']}")
    print(f"Duration: {summary['duration_s']} s  |  Dropouts: {summary['dropouts']}")
    print(f"Topics: {topics['num_topics']}  |  Params: {summary['num_params']}")
    print(f"Warnings/errors: {summary['num_warnings_or_errors']}")

    print("\nTop 10 topics by sample count:")
    busiest = sorted(topics["topics"], key=lambda t: t["num_samples"], reverse=True)
    for t in busiest[:10]:
        print(f"  {t['name']:<28} {t['num_samples']:>8} samples")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
