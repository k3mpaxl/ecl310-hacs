"""A266.10 V03 (issue 35): what its profile changes about the entities.

Simulated from the captured A237.1 image, refusing what A266.10 lacks and
reporting A266.10 V03 as its application, like the real one would.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from modbus_connection.mock import MockModbusConnection

from .conftest import HOLDING
from .test_integration import entity_ids, setup_entry

A266 = "a266_10_v03"

#: S2, S4 and S6 as the A266.10 controller would measure them (hundredths).
A266_SENSORS = {10201: 3810, 10203: 5230, 10205: 2950}


@pytest.mark.parametrize("application", [A266])
@pytest.mark.parametrize("register_image", [{**HOLDING, **A266_SENSORS}])
async def test_a266_names_its_sensors_pumps_and_valves(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """S2/S4/S6 carry A266.10's meaning; pumps and valves as wired (issue 35).

    The owner's installation: relay 1 the hot water circulation pump (P1),
    relay 2 the heating pump (P2), triacs 1/2 the hot water valve (M1), triacs
    3/4 the heating valve (M2).
    """
    entry = await setup_entry(hass, connections)
    assert entry.data["application"] == A266
    ids = entity_ids(hass, entry)
    state = hass.states.get

    assert state(ids["secondary_return_temperature"]).state == "38.1"
    assert state(ids["hot_water_flow_temperature"]).state == "52.3"
    assert state(ids["hot_water_return_temperature"]).state == "29.5"
    assert "storage_temperature" not in ids

    attributes = {key: state(ids[key]).attributes for key in ids if state(ids[key])}
    assert attributes["circulation_pump"]["terminal"] == "relay 1"
    assert attributes["heating_pump"]["terminal"] == "relay 2"
    assert "heating_pump_override" in ids
    assert "storage_charge_pump" not in ids
    assert "heat_available" in ids

    registry = er.async_get(hass)
    valves = {
        "hot_water_valve_open": "triac_1",
        "hot_water_valve_close": "triac_2",
        "valve_open": "triac_3",
        "valve_close": "triac_4",
    }
    for key in valves:
        # Pulsed all day, so off by default - but named.
        assert registry.async_get(ids[key]).disabled_by is not None
    for number in (3, 4, 5, 6):
        assert registry.async_get(ids[f"relay_{number}"]).disabled_by is not None
    assert "relay_1" not in ids


async def test_a237_keeps_its_pumps_and_hides_the_spare_relays(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """The captured A237.1 controller is unchanged."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    for key in ("heating_pump", "storage_charge_pump", "circulation_pump"):
        assert key in ids
    assert "heat_available" in ids
    assert "hot_water_flow_temperature" not in ids
    registry = er.async_get(hass)
    assert registry.async_get(ids["relay_4"]).disabled_by is not None
