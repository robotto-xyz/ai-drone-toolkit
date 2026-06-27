"""MAVSDK-facing drone-control layer for PX4 SITL.

This module owns the long-lived MAVSDK ``System`` instance and raw action calls.
It knows nothing about MCP. Every command validates through
``robotto_drone_core.safety`` before touching MAVSDK and returns
JSON-serializable dicts for thin MCP wrappers to relay.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from mavsdk import System
from mavsdk.action import ActionError

from robotto_drone_core import frames, safety

from . import config


class SimDrone:
    """Lazy, reusable MAVSDK connection to one local PX4 SITL instance."""

    def __init__(self, address: str = config.DEFAULT_SIM_ADDRESS) -> None:
        self.address = address
        self._system: System | None = None
        self._connected = False
        self._home_lat_deg: float | None = None
        self._home_lon_deg: float | None = None
        self._home_amsl_m: float | None = None

    @property
    def system(self) -> System:
        if self._system is None:
            self._system = System()
        return self._system

    async def _first(self, stream: AsyncIterator[Any], timeout_s: float) -> Any:
        async def read_one() -> Any:
            async for item in stream:
                return item
            raise RuntimeError("MAVSDK telemetry stream ended unexpectedly")

        return await asyncio.wait_for(read_one(), timeout=timeout_s)

    async def _wait_connected(self, timeout_s: float) -> dict[str, Any]:
        async def wait() -> dict[str, Any]:
            async for state in self.system.core.connection_state():
                if state.is_connected:
                    return safety.ok(connected=True)
            return safety.refused("MAVSDK connection stream ended before connecting")

        try:
            return await asyncio.wait_for(wait(), timeout=timeout_s)
        except TimeoutError:
            return safety.refused(f"Timed out waiting for PX4 SITL after {timeout_s:g}s")

    async def _wait_healthy(self, timeout_s: float) -> dict[str, Any]:
        async def wait() -> dict[str, Any]:
            async for health in self.system.telemetry.health():
                result = safety.check_arming_preconditions(
                    is_global_position_ok=health.is_global_position_ok,
                    is_home_position_ok=health.is_home_position_ok,
                )
                if result["ok"]:
                    return result
            return safety.refused("MAVSDK health stream ended before readiness")

        try:
            return await asyncio.wait_for(wait(), timeout=timeout_s)
        except TimeoutError:
            return safety.refused(
                "Timed out waiting for healthy global and home position after "
                f"{timeout_s:g}s"
            )

    async def _cache_home(self, timeout_s: float) -> dict[str, Any]:
        try:
            home = await self._first(self.system.telemetry.home(), timeout_s)
        except TimeoutError:
            return safety.refused(f"Timed out waiting for home position after {timeout_s:g}s")

        self._home_lat_deg = float(home.latitude_deg)
        self._home_lon_deg = float(home.longitude_deg)
        self._home_amsl_m = float(home.absolute_altitude_m)
        return safety.ok(
            home={
                "latitude_deg": self._home_lat_deg,
                "longitude_deg": self._home_lon_deg,
                "absolute_altitude_m": self._home_amsl_m,
            }
        )

    async def connect(
        self,
        address: str | None = None,
        *,
        timeout_s: float = config.DEFAULT_CONNECT_TIMEOUT_S,
    ) -> dict[str, Any]:
        """Connect to local PX4 SITL and wait for arming-ready health."""

        if address is not None and address != self.address:
            self.address = address
            self._system = None
            self._connected = False
            self._home_lat_deg = None
            self._home_lon_deg = None
            self._home_amsl_m = None

        sim_gate = safety.check_simulation_only(self.address)
        if not sim_gate["ok"]:
            return sim_gate

        if not self._connected:
            await self.system.connect(system_address=self.address)
            connected = await self._wait_connected(timeout_s)
            if not connected["ok"]:
                return connected
            self._connected = True

        healthy = await self._wait_healthy(timeout_s)
        if not healthy["ok"]:
            return healthy

        home = await self._cache_home(timeout_s)
        if not home["ok"]:
            return home

        return safety.ok(address=self.address, connected=True, home=home["home"])

    async def get_state(self) -> dict[str, Any]:
        """Return current read-only drone state as JSON-serializable data."""

        connected = await self.connect()
        if not connected["ok"]:
            return connected

        try:
            armed = await self._first(self.system.telemetry.armed(), 5.0)
            flight_mode = await self._first(self.system.telemetry.flight_mode(), 5.0)
            position = await self._first(self.system.telemetry.position(), 5.0)
            battery = await self._first(self.system.telemetry.battery(), 5.0)
        except TimeoutError as exc:
            return safety.refused(f"Timed out reading telemetry: {exc}")

        return safety.ok(
            state={
                "armed": bool(armed),
                "flight_mode": str(flight_mode),
                "position": {
                    "latitude_deg": float(position.latitude_deg),
                    "longitude_deg": float(position.longitude_deg),
                    "absolute_altitude_m": float(position.absolute_altitude_m),
                    "relative_altitude_m": float(position.relative_altitude_m),
                },
                "battery": {
                    "remaining_percent": float(battery.remaining_percent),
                },
            }
        )

    async def _current_health(self) -> dict[str, Any]:
        try:
            health = await self._first(self.system.telemetry.health(), 5.0)
        except TimeoutError as exc:
            return safety.refused(f"Timed out reading health: {exc}")
        return safety.check_arming_preconditions(
            is_global_position_ok=health.is_global_position_ok,
            is_home_position_ok=health.is_home_position_ok,
        )

    async def _wait_for_altitude(
        self,
        altitude_m: float,
        *,
        timeout_s: float = config.DEFAULT_REACH_TIMEOUT_S,
    ) -> dict[str, Any]:
        async def wait() -> dict[str, Any]:
            async for position in self.system.telemetry.position():
                current_altitude_m = float(position.relative_altitude_m)
                if abs(current_altitude_m - altitude_m) <= 1.0:
                    return safety.ok(relative_altitude_m=current_altitude_m)
                await asyncio.sleep(config.DEFAULT_POLL_INTERVAL_S)
            return safety.refused("Position stream ended before reaching altitude")

        try:
            return await asyncio.wait_for(wait(), timeout_s)
        except TimeoutError:
            return safety.refused(
                f"Timed out before reaching {altitude_m:g} m relative altitude"
            )

    async def takeoff(self, altitude_m: float) -> dict[str, Any]:
        """Arm promptly and take off to a validated relative altitude."""

        connected = await self.connect()
        if not connected["ok"]:
            return connected

        altitude = safety.clamp_altitude(altitude_m, config.SAFETY_LIMITS)
        if not altitude["ok"]:
            return altitude

        arming = await self._current_health()
        if not arming["ok"]:
            return arming

        try:
            await self.system.action.set_takeoff_altitude(altitude["altitude_m"])
            await self.system.action.arm()
            await self.system.action.takeoff()
        except ActionError as exc:
            return {
                "ok": False,
                "refused": False,
                "reason": f"MAVSDK action failed during takeoff: {exc}",
            }

        reached = await self._wait_for_altitude(altitude["altitude_m"])
        if not reached["ok"]:
            return {**reached, "accepted": True, "target_altitude_m": altitude["altitude_m"]}

        return safety.ok(
            action="takeoff",
            accepted=True,
            target_altitude_m=altitude["altitude_m"],
            **reached,
        )

    async def land(self) -> dict[str, Any]:
        """Land at the current position."""

        connected = await self.connect()
        if not connected["ok"]:
            return connected

        try:
            armed = await self._first(self.system.telemetry.armed(), 5.0)
        except TimeoutError as exc:
            return safety.refused(f"Timed out checking armed state: {exc}")
        if not armed:
            return safety.refused("Cannot land because the simulated drone is not armed")

        try:
            await self.system.action.land()
        except ActionError as exc:
            return {
                "ok": False,
                "refused": False,
                "reason": f"MAVSDK action failed during land: {exc}",
            }

        return safety.ok(action="land", accepted=True)

    def _home_ready(self) -> bool:
        return (
            self._home_lat_deg is not None
            and self._home_lon_deg is not None
            and self._home_amsl_m is not None
        )

    async def _wait_for_goto(
        self,
        *,
        target_north_m: float,
        target_east_m: float,
        target_altitude_m: float,
        timeout_s: float,
    ) -> dict[str, Any]:
        if not self._home_ready():
            return safety.refused("Home position is not cached; call connect first")

        async def wait() -> dict[str, Any]:
            async for position in self.system.telemetry.position():
                current_north_m, current_east_m = frames.latlon_to_offset(
                    self._home_lat_deg or 0.0,
                    self._home_lon_deg or 0.0,
                    float(position.latitude_deg),
                    float(position.longitude_deg),
                )
                current_altitude_m = float(position.relative_altitude_m)
                if frames.reached_target(
                    current_north_m=current_north_m,
                    current_east_m=current_east_m,
                    current_altitude_m=current_altitude_m,
                    target_north_m=target_north_m,
                    target_east_m=target_east_m,
                    target_altitude_m=target_altitude_m,
                ):
                    return safety.ok(
                        current_north_m=current_north_m,
                        current_east_m=current_east_m,
                        current_altitude_m=current_altitude_m,
                    )
                await asyncio.sleep(config.DEFAULT_POLL_INTERVAL_S)
            return safety.refused("Position stream ended before reaching goto target")

        try:
            return await asyncio.wait_for(wait(), timeout_s)
        except TimeoutError:
            return safety.refused(
                "Timed out before reaching goto target "
                f"north={target_north_m:g} east={target_east_m:g} "
                f"altitude={target_altitude_m:g}"
            )

    async def goto(
        self,
        north_m: float,
        east_m: float,
        altitude_m: float,
        *,
        yaw_deg: float = config.DEFAULT_YAW_DEG,
        timeout_s: float = config.DEFAULT_REACH_TIMEOUT_S,
    ) -> dict[str, Any]:
        """Fly to a meters-from-home target after safety and frame conversion."""

        connected = await self.connect()
        if not connected["ok"]:
            return connected

        geofence = safety.check_geofence(north_m, east_m, config.SAFETY_LIMITS)
        if not geofence["ok"]:
            return geofence

        altitude = safety.clamp_altitude(altitude_m, config.SAFETY_LIMITS)
        if not altitude["ok"]:
            return altitude

        if not self._home_ready():
            return safety.refused("Home position is not cached; call connect first")

        target_lat_deg, target_lon_deg = frames.offset_to_latlon(
            self._home_lat_deg or 0.0,
            self._home_lon_deg or 0.0,
            north_m,
            east_m,
        )
        target_amsl_m = frames.relative_to_amsl(
            altitude["altitude_m"],
            self._home_amsl_m or 0.0,
        )

        try:
            await self.system.action.goto_location(
                target_lat_deg,
                target_lon_deg,
                target_amsl_m,
                yaw_deg,
            )
        except ActionError as exc:
            return {
                "ok": False,
                "refused": False,
                "reason": f"MAVSDK action failed during goto: {exc}",
            }

        reached = await self._wait_for_goto(
            target_north_m=north_m,
            target_east_m=east_m,
            target_altitude_m=altitude["altitude_m"],
            timeout_s=timeout_s,
        )
        if not reached["ok"]:
            return {
                **reached,
                "accepted": True,
                "target": {
                    "north_m": north_m,
                    "east_m": east_m,
                    "relative_altitude_m": altitude["altitude_m"],
                    "absolute_altitude_m": target_amsl_m,
                    "latitude_deg": target_lat_deg,
                    "longitude_deg": target_lon_deg,
                },
            }

        return safety.ok(
            action="goto",
            accepted=True,
            target={
                "north_m": north_m,
                "east_m": east_m,
                "relative_altitude_m": altitude["altitude_m"],
                "absolute_altitude_m": target_amsl_m,
                "latitude_deg": target_lat_deg,
                "longitude_deg": target_lon_deg,
            },
            **reached,
        )


drone = SimDrone()
