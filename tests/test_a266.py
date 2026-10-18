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
async def test_a266_names_its_sensors_and_hides_unknown_pumps(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """S2/S4/S6 carry A266.10's meaning; relays show by number, unnamed."""
    entry = await setup_entry(hass, connections)
    assert entry.data["application"] == A266
    ids = entity_ids(hass, entry)
    state = hass.states.get

    assert state(ids["secondary_return_temperature"]).state == "38.1"
    assert state(ids["hot_water_flow_temperature"]).state == "52.3"
    assert state(ids["hot_water_return_temperature"]).state == "29.5"
    assert "storage_temperature" not in ids

    # Which relay drives which pump is not known for A266 yet: no pump
    # entities, no overrides, no "heat available" - the relays by number.
    for key in ("heating_pump", "circulation_pump", "heating_pump_override"):
        assert key not in ids
    assert "heat_available" not in ids
    registry = er.async_get(hass)
    for number in range(1, 7):
        relay = registry.async_get(ids[f"relay_{number}"])
        assert relay.disabled_by is None


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
