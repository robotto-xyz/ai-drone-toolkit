"""Simulator-free tests for SimDrone connection lifecycle.

These use a tiny fake MAVSDK ``System`` so we can assert connection behavior
(idempotency, home caching, speed-cap wiring) without PX4 SITL running.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from px4_sitl_mcp import config
from px4_sitl_mcp.drone import SimDrone


async def _stream(items: list[Any]) -> AsyncIterator[Any]:
    for item in items:
        yield item


class _Conn:
    is_connected = True


class _Health:
    is_global_position_ok = True
    is_home_position_ok = True


class _Home:
    latitude_deg = 47.397742
    longitude_deg = 8.545594
    absolute_altitude_m = 488.0


class _FakeCore:
    def connection_state(self) -> AsyncIterator[Any]:
        return _stream([_Conn()])


class _FakeTelemetry:
    def __init__(self, counters: dict[str, Any]) -> None:
        self._counters = counters

    def health(self) -> AsyncIterator[Any]:
        return _stream([_Health()])

    def home(self) -> AsyncIterator[Any]:
        self._counters["home"] += 1
        return _stream([_Home()])


class _FakeAction:
    def __init__(self, counters: dict[str, Any]) -> None:
        self._counters = counters

    async def set_current_speed(self, speed_m_s: float) -> None:
        self._counters["set_speed"] += 1
        self._counters["last_speed"] = speed_m_s


class _FakeSystem:
    def __init__(self, counters: dict[str, Any]) -> None:
        self._counters = counters
        self.core = _FakeCore()
        self.telemetry = _FakeTelemetry(counters)
        self.action = _FakeAction(counters)

    async def connect(self, *, system_address: str | None = None) -> None:
        self._counters["connect"] += 1


class _InjectedDrone(SimDrone):
    """SimDrone whose MAVSDK System is always a counter-backed fake.

    Overriding the lazy ``system`` property keeps the fake in place even after
    ``connect()`` resets ``_system`` on an address change.
    """

    def __init__(self, counters: dict[str, Any]) -> None:
        super().__init__()
        self._counters = counters

    @property
    def system(self):  # type: ignore[override]
        if self._system is None:
            self._system = _FakeSystem(self._counters)
        return self._system


def _drone_with_fake() -> tuple[SimDrone, dict[str, Any]]:
    counters = {"home": 0, "set_speed": 0, "connect": 0, "last_speed": None}
    return _InjectedDrone(counters), counters


def test_connect_caches_home_and_sets_speed_once_across_calls():
    drone, counters = _drone_with_fake()

    async def scenario() -> list[dict[str, Any]]:
        return [await drone.connect() for _ in range(3)]

    results = asyncio.run(scenario())

    assert all(result["ok"] for result in results)
    # Idempotent: home is cached and the speed cap is pushed exactly once,
    # never re-walked mid-flight on subsequent connect() calls.
    assert counters["home"] == 1
    assert counters["set_speed"] == 1
    assert counters["last_speed"] == config.SAFETY_LIMITS.max_speed_ms
    assert results[1]["ready"] is True


def test_connect_reset_on_address_change_recaches_home():
    drone, counters = _drone_with_fake()

    async def scenario() -> None:
        await drone.connect()
        # Re-pointing at a different valid SITL endpoint must reset readiness
        # and re-cache home for the new vehicle.
        await drone.connect("udpin://0.0.0.0:14541")

    asyncio.run(scenario())

    assert counters["home"] == 2
    assert counters["set_speed"] == 2
