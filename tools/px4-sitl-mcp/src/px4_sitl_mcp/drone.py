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

from grpc.aio import AioRpcError
from mavsdk import System
from mavsdk.action import ActionError

from robotto_drone_core import frames, safety, survey

from . import config

# MAVSDK-Python surfaces two failure classes we must never let escape as raw
# tracebacks (AGENTS.md landmine): ActionError for command rejections, and
# grpc.aio.AioRpcError for transport-level faults (server crash, connection
# reset, port contention). Both convert to structured {"ok": false} results.
MAVSDK_CALL_ERRORS = (ActionError, AioRpcError)


class SimDrone:
    """Lazy, reusable MAVSDK connection to one local PX4 SITL instance."""

    def __init__(self, address: str = config.DEFAULT_SIM_ADDRESS) -> None:
        self.address = address
        self._system: System | None = None
        self._connected = False
        self._ready = False
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
        return safety.ok(home=self._home())

    def _home(self) -> dict[str, float] | None:
        if not self._home_ready():
            return None
        return {
            "latitude_deg": self._home_lat_deg or 0.0,
            "longitude_deg": self._home_lon_deg or 0.0,
            "absolute_altitude_m": self._home_amsl_m or 0.0,
        }

    async def _apply_speed_limit(self) -> dict[str, Any]:
        """Validate and push the configured speed cap to PX4 once on connect.

        This is where the shared ``check_speed`` safety bound actually reaches
        the vehicle: the geofence/altitude clamps gate position, this bounds how
        fast PX4 flies between waypoints. MAVSDK's ``set_current_speed`` sets the
        speed used for ``goto_location``/reposition; it is ephemeral (not stored
        on the drone), so we re-apply it on each fresh connection.
        """

        speed = safety.check_speed(
            config.SAFETY_LIMITS.max_speed_ms,
            config.SAFETY_LIMITS,
        )
        if not speed["ok"]:
            return speed
        try:
            await self.system.action.set_current_speed(speed["speed_ms"])
        except MAVSDK_CALL_ERRORS as exc:
            return {
                "ok": False,
                "refused": False,
                "reason": f"MAVSDK action failed setting speed cap: {exc}",
            }
        return safety.ok(max_speed_ms=speed["speed_ms"])

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
            self._ready = False
            self._home_lat_deg = None
            self._home_lon_deg = None
            self._home_amsl_m = None

        sim_gate = safety.check_simulation_only(self.address)
        if not sim_gate["ok"]:
            return sim_gate

        # Idempotent fast path: once connected + healthy + home cached, never
        # re-walk the health stream, re-cache home, or re-set the speed cap.
        # Re-running these mid-flight (e.g. on every goto in a survey) is at best
        # wasteful and at worst drifts the AMSL math if home re-caches differently.
        if self._ready:
            return safety.ok(
                address=self.address,
                connected=True,
                ready=True,
                home=self._home(),
            )

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

        speed = await self._apply_speed_limit()
        if not speed["ok"]:
            return speed

        self._ready = True
        return safety.ok(address=self.address, connected=True, ready=True, home=home["home"])

    def summary(self) -> dict[str, Any]:
        """Return local connection bookkeeping without touching MAVSDK."""

        return {
            "address": self.address,
            "connected": self._connected,
            "ready": self._ready,
            "home_cached": self._home_ready(),
        }

    def close(self) -> dict[str, Any]:
        """Stop the auto-started MAVSDK server and reset connection state.

        MAVSDK-Python auto-spawns a ``mavsdk_server`` subprocess that otherwise
        keeps the interpreter alive on exit (scripts appear to "hang") and leaves
        the local UDP endpoint bound, which makes the next connection fail with
        "Address already in use". MAVSDK exposes no public stop API, so we call
        its documented-internal stop defensively and drop our reference. Safe to
        call even if never connected; long-lived servers (the MCP process) don't
        need it but may call it for clean shutdown.
        """

        system = self._system
        if system is not None:
            stop = getattr(system, "_stop_mavsdk_server", None)
            if callable(stop):
                try:
                    stop()
                except Exception:
                    pass
            # Avoid System.__del__ re-stopping during interpreter shutdown,
            # which raises a harmless ImportError as modules unload.
            try:
                system._server_process = None
            except Exception:
                pass
        self._system = None
        self._connected = False
        self._ready = False
        return safety.ok(closed=True)

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
        # Consume the position stream at its native rate (no sleep in the loop).
        # MAVSDK's telemetry.position() pushes at ~tens of Hz; awaiting a sleep
        # between frames lets the gRPC backlog grow so we read ever-staler frames
        # and never observe the live climb before the timeout. Every frame is a
        # cheap comparison, so draining continuously keeps us on current data.
        async def wait() -> dict[str, Any]:
            async for position in self.system.telemetry.position():
                current_altitude_m = float(position.relative_altitude_m)
                # Reached once climbed to within tolerance below target. PX4
                # settles slightly above the commanded takeoff altitude, so an
                # at-or-above check avoids false timeouts on that overshoot.
                if current_altitude_m >= altitude_m - config.TAKEOFF_REACH_TOLERANCE_M:
                    return safety.ok(relative_altitude_m=current_altitude_m)
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
        except MAVSDK_CALL_ERRORS as exc:
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
        except MAVSDK_CALL_ERRORS as exc:
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

        # Drain the stream at its native rate (see _wait_for_altitude): sleeping
        # between frames backs up the gRPC buffer and makes us act on stale
        # positions, so the vehicle reaches the waypoint without us observing it.
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
                    horizontal_tolerance_m=config.GOTO_HORIZONTAL_TOLERANCE_M,
                    vertical_tolerance_m=config.GOTO_VERTICAL_TOLERANCE_M,
                ):
                    return safety.ok(
                        current_north_m=current_north_m,
                        current_east_m=current_east_m,
                        current_altitude_m=current_altitude_m,
                    )
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
        except MAVSDK_CALL_ERRORS as exc:
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

    async def fly_survey_pattern(
        self,
        width_m: float,
        height_m: float,
        spacing_m: float,
        altitude_m: float,
    ) -> dict[str, Any]:
        """Fly a centered lawnmower survey, validating the whole path first."""

        try:
            waypoints = survey.generate_lawnmower(
                width_m=width_m,
                height_m=height_m,
                spacing_m=spacing_m,
                altitude_m=altitude_m,
            )
        except ValueError as exc:
            return safety.refused(str(exc))

        validation = survey.validate_survey_waypoints(
            waypoints,
            config.SAFETY_LIMITS,
        )
        if not validation["ok"]:
            return validation

        completed: list[dict[str, Any]] = []
        for index, waypoint in enumerate(waypoints):
            result = await self.goto(
                waypoint["north_m"],
                waypoint["east_m"],
                waypoint["altitude_m"],
            )
            if not result["ok"]:
                return {
                    **result,
                    "action": "fly_survey_pattern",
                    "failed_waypoint_index": index,
                    "completed_waypoints": completed,
                }
            completed.append(
                {
                    "index": index,
                    "north_m": waypoint["north_m"],
                    "east_m": waypoint["east_m"],
                    "altitude_m": waypoint["altitude_m"],
                }
            )

        home = await self.goto(0.0, 0.0, altitude_m)
        if not home["ok"]:
            return {
                **home,
                "action": "fly_survey_pattern",
                "completed_waypoints": completed,
                "return_home_failed": True,
            }

        return safety.ok(
            action="fly_survey_pattern",
            accepted=True,
            num_waypoints=len(waypoints),
            completed_waypoints=completed,
            returned_home=True,
        )


class DroneFleet:
    """Manage multiple local PX4 SITL connections keyed by drone id."""

    def __init__(
        self,
        *,
        drone_factory: type[SimDrone] = SimDrone,
        default_drone_id: str = config.DEFAULT_DRONE_ID,
    ) -> None:
        self.drone_factory = drone_factory
        self.default_drone_id = default_drone_id
        self._drones: dict[str, SimDrone] = {
            default_drone_id: drone_factory(config.DEFAULT_SIM_ADDRESS)
        }

    @property
    def default_drone(self) -> SimDrone:
        return self._drones[self.default_drone_id]

    def get_drone(
        self,
        drone_id: str = config.DEFAULT_DRONE_ID,
        address: str | None = None,
    ) -> SimDrone:
        if drone_id not in self._drones:
            self._drones[drone_id] = self.drone_factory(
                address or config.DEFAULT_SIM_ADDRESS
            )
        return self._drones[drone_id]

    def list_drones(self) -> dict[str, Any]:
        return safety.ok(
            drones={
                drone_id: drone.summary()
                for drone_id, drone in sorted(self._drones.items())
            }
        )

    def close_all(self) -> dict[str, Any]:
        """Stop every drone's MAVSDK server (clean shutdown for scripts)."""

        for drone in self._drones.values():
            close = getattr(drone, "close", None)
            if callable(close):
                close()
        return safety.ok(closed=True)

    async def connect_drone(
        self,
        drone_id: str,
        address: str,
    ) -> dict[str, Any]:
        gate = safety.check_simulation_only(address)
        if not gate["ok"]:
            return {**gate, "drone_id": drone_id}

        target = self.get_drone(drone_id, address)
        result = await target.connect(address)
        return {**result, "drone_id": drone_id}

    async def connect_drones(self, count: int) -> dict[str, Any]:
        if count <= 0:
            return safety.refused("count must be positive")
        if count > len(config.DEFAULT_MULTI_DRONE_ADDRESSES):
            return safety.refused(
                "count exceeds documented default multi-drone addresses",
                max_count=len(config.DEFAULT_MULTI_DRONE_ADDRESSES),
            )

        results: dict[str, Any] = {}
        for drone_id, address in list(config.DEFAULT_MULTI_DRONE_ADDRESSES.items())[
            :count
        ]:
            results[drone_id] = await self.connect_drone(drone_id, address)
        ok = all(result["ok"] for result in results.values())
        return {
            "ok": ok,
            "refused": not ok,
            "results": results,
        }

    async def command_drone(
        self,
        drone_id: str,
        action: str,
        *,
        altitude_m: float | None = None,
        north_m: float | None = None,
        east_m: float | None = None,
        width_m: float | None = None,
        height_m: float | None = None,
        spacing_m: float | None = None,
    ) -> dict[str, Any]:
        normalized = action.lower()
        supported_actions = [
            "get_state",
            "takeoff",
            "goto",
            "land",
            "fly_survey_pattern",
        ]
        if normalized not in supported_actions:
            return safety.refused(
                f"Unsupported per-drone action: {action}",
                supported_actions=supported_actions,
            )

        target = self.get_drone(drone_id)

        if normalized == "get_state":
            result = await target.get_state()
        elif normalized == "takeoff":
            if altitude_m is None:
                return safety.refused("takeoff requires altitude_m")
            result = await target.takeoff(altitude_m)
        elif normalized == "goto":
            if altitude_m is None or north_m is None or east_m is None:
                return safety.refused("goto requires north_m, east_m, and altitude_m")
            result = await target.goto(north_m, east_m, altitude_m)
        elif normalized == "land":
            result = await target.land()
        elif normalized == "fly_survey_pattern":
            if (
                width_m is None
                or height_m is None
                or spacing_m is None
                or altitude_m is None
            ):
                return safety.refused(
                    "fly_survey_pattern requires width_m, height_m, spacing_m, "
                    "and altitude_m"
                )
            result = await target.fly_survey_pattern(
                width_m,
                height_m,
                spacing_m,
                altitude_m,
            )

        return {**result, "drone_id": drone_id, "command": normalized}


fleet = DroneFleet()
drone = fleet.default_drone
