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


class _Position:
    def __init__(self, relative_altitude_m: float) -> None:
        self.relative_altitude_m = relative_altitude_m
        self.absolute_altitude_m = relative_altitude_m
        self.latitude_deg = _Home.latitude_deg
        self.longitude_deg = _Home.longitude_deg


class _FakeTelemetry:
    def __init__(self, counters: dict[str, Any]) -> None:
        self._counters = counters

    def health(self) -> AsyncIterator[Any]:
        return _stream([_Health()])

    def home(self) -> AsyncIterator[Any]:
        self._counters["home"] += 1
        return _stream([_Home()])

    def position(self) -> AsyncIterator[Any]:
        alts = self._counters.get("altitudes", [0.0])
        return _stream([_Position(a) for a in alts])


class _FakeAction:
    def __init__(self, counters: dict[str, Any]) -> None:
        self._counters = counters

    async def set_current_speed(self, speed_m_s: float) -> None:
        self._counters["set_speed"] += 1
        self._counters["last_speed"] = speed_m_s

    async def set_takeoff_altitude(self, altitude_m: float) -> None:
        self._counters["set_takeoff_altitude"] = altitude_m

    async def arm(self) -> None:
        self._counters["armed"] = True

    async def takeoff(self) -> None:
        if self._counters.get("takeoff_raises") is not None:
            raise self._counters["takeoff_raises"]


class _FakeSystem:
    def __init__(self, counters: dict[str, Any]) -> None:
        self._counters = counters
        self._server_process = object()
        self.core = _FakeCore()
        self.telemetry = _FakeTelemetry(counters)
        self.action = _FakeAction(counters)

    async def connect(self, *, system_address: str | None = None) -> None:
        self._counters["connect"] += 1

    def _stop_mavsdk_server(self) -> None:
        self._counters["stopped"] = self._counters.get("stopped", 0) + 1


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


def test_takeoff_converts_transport_error_to_structured_result():
    # MAVSDK can raise grpc.aio.AioRpcError (transport faults: server crash,
    # connection reset, port contention), not just ActionError. These must be
    # caught and returned as a structured {"ok": false} result, never escape as
    # a raw traceback (AGENTS.md "never let a raw exception escape a tool").
    from grpc import StatusCode
    from grpc.aio import AioRpcError, Metadata

    drone, counters = _drone_with_fake()
    counters["takeoff_raises"] = AioRpcError(
        StatusCode.UNAVAILABLE,
        Metadata(),
        Metadata(),
        details="Stream removed (recvmsg:Connection reset by peer)",
    )

    result = asyncio.run(drone.takeoff(15))

    assert result["ok"] is False
    assert result["refused"] is False
    assert "MAVSDK action failed during takeoff" in result["reason"]
    assert "Stream removed" in result["reason"]


def test_close_stops_mavsdk_server_and_resets_state():
    # MAVSDK auto-starts a mavsdk_server subprocess that otherwise hangs the
    # interpreter on exit and leaves the UDP port bound. close() must stop it
    # and reset connection state so a later connect() starts fresh.
    drone, counters = _drone_with_fake()
    asyncio.run(drone.connect())

    result = drone.close()

    assert result["ok"] is True
    assert counters["stopped"] == 1
    assert drone._system is None
    assert drone._connected is False
    assert drone._ready is False


def test_wait_for_altitude_handles_takeoff_overshoot():
    # PX4 auto-takeoff settles ABOVE the commanded altitude (observed: 15 m
    # command -> holds at ~16.5 m). The reached-check must treat that overshoot
    # as success, not poll forever and false-timeout.
    drone, counters = _drone_with_fake()
    counters["altitudes"] = [1.5, 9.7, 13.75, 15.49, 16.16, 16.51, 16.51]

    result = asyncio.run(drone._wait_for_altitude(15.0, timeout_s=5.0))

    assert result["ok"] is True
    # First sample at or above target - tolerance (15 - 1 = 14) is 15.49.
    assert result["relative_altitude_m"] == 15.49


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
