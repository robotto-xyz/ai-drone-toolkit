"""robotto-drone-core: shared parsers and utilities for the AI Drone Toolkit.

Common, MCP-agnostic logic lives here so individual tools (MCP servers, CLIs,
web apps) can depend on it instead of duplicating parsing code. Today this
exposes PX4 ULog parsing via :mod:`robotto_drone_core.ulog_tools`.
"""

from __future__ import annotations

from . import ulog_tools
from .ulog_tools import ULogError, get_log_summary, list_log_topics

__version__ = "0.1.0"

__all__ = [
    "ulog_tools",
    "ULogError",
    "get_log_summary",
    "list_log_topics",
]
