from __future__ import annotations

import asyncio
from typing import Any

from px4_sitl_mcp import config
from px4_sitl_mcp.drone import DroneFleet
from robotto_drone_core import safety


class FakeDrone:
    def __init__(self, address: str = config.DEFAULT_SIM_ADDRESS) -> None:
        self.address = address
        self.connected = False
        self.calls: list[tuple[str, Any]] = []

    def summary(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "connected": self.connected,
            "home_cached": self.connected,
        }

    async def connect(self, address: str | None = None) -> dict[str, Any]:
        if address is not None:
            self.address = address
        self.connected = True
        self.calls.append(("connect", self.address))
        return safety.ok(address=self.address, connected=True)

    async def get_state(self) -> dict[str, Any]:
        self.calls.append(("get_state", None))
        return safety.ok(state={"armed": False})

    async def takeoff(self, altitude_m: float) -> dict[str, Any]:
        self.calls.append(("takeoff", altitude_m))
        return safety.ok(action="takeoff", target_altitude_m=altitude_m)

    async def goto(self, north_m: float, east_m: float, altitude_m: float) -> dict[str, Any]:
        self.calls.append(("goto", (north_m, east_m, altitude_m)))
        return safety.ok(action="goto")

    async def land(self) -> dict[str, Any]:
        self.calls.append(("land", None))
        return safety.ok(action="land")

    async def fly_survey_pattern(
        self,
        width_m: float,
        height_m: float,
        spacing_m: float,
        altitude_m: float,
    ) -> dict[str, Any]:
        self.calls.append(("fly_survey_pattern", (width_m, height_m, spacing_m, altitude_m)))
        return safety.ok(action="fly_survey_pattern")


def test_fleet_starts_with_default_drone():
    fleet = DroneFleet(drone_factory=FakeDrone)

    drones = fleet.list_drones()["drones"]

    assert list(drones) == [config.DEFAULT_DRONE_ID]
    assert drones[config.DEFAULT_DRONE_ID]["address"] == config.DEFAULT_SIM_ADDRESS


def test_connect_drone_rejects_bad_address_without_creating_drone():
    fleet = DroneFleet(drone_factory=FakeDrone)

    result = asyncio.run(fleet.connect_drone("bad", "udp://192.168.1.10:14540"))

    assert result["ok"] is False
    assert result["refused"] is True
    assert result["drone_id"] == "bad"
    assert "bad" not in fleet.list_drones()["drones"]


def test_connect_drone_tracks_ids_independently():
    fleet = DroneFleet(drone_factory=FakeDrone)

    one = asyncio.run(fleet.connect_drone("drone-1", "udpin://0.0.0.0:14540"))
    two = asyncio.run(fleet.connect_drone("drone-2", "udpin://0.0.0.0:14541"))

    assert one["ok"] is True
    assert two["ok"] is True
    drones = fleet.list_drones()["drones"]
    assert drones["drone-1"]["address"] == "udpin://0.0.0.0:14540"
    assert drones["drone-2"]["address"] == "udpin://0.0.0.0:14541"


def test_connect_drones_uses_documented_defaults():
    fleet = DroneFleet(drone_factory=FakeDrone)

    result = asyncio.run(fleet.connect_drones(2))

    assert result["ok"] is True
    assert set(result["results"]) == {"drone-1", "drone-2"}
    drones = fleet.list_drones()["drones"]
    assert drones["drone-1"]["address"] == "udpin://0.0.0.0:14540"
    assert drones["drone-2"]["address"] == "udpin://0.0.0.0:14541"


def test_command_drone_dispatches_existing_actions():
    fleet = DroneFleet(drone_factory=FakeDrone)

    result = asyncio.run(
        fleet.command_drone("alpha", "goto", north_m=1, east_m=2, altitude_m=3)
    )

    assert result["ok"] is True
    assert result["drone_id"] == "alpha"
    assert result["command"] == "goto"
    assert fleet.get_drone("alpha").calls[-1] == ("goto", (1, 2, 3))


def test_command_drone_refuses_unknown_action():
    fleet = DroneFleet(drone_factory=FakeDrone)

    result = asyncio.run(fleet.command_drone("alpha", "formation"))

    assert result["ok"] is False
    assert result["refused"] is True
    assert "Unsupported per-drone action" in result["reason"]
    assert "alpha" not in fleet.list_drones()["drones"]
