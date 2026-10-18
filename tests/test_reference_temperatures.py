"""What the controller is working with right now: computed, read-only values."""

from __future__ import annotations

import pytest
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from modbus_connection.mock import MockModbusConnection

from .conftest import HOLDING
from .test_integration import entity_ids, setup_entry


async def test_the_a237_shows_its_targets(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """Desired flow and tank, filtered outdoor, the return limit in force."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    state = hass.states.get
    assert state(ids["desired_flow_temperature"]).state == "10.0"
    assert state(ids["filtered_outdoor_temperature"]).state == "13.61"
    assert state(ids["return_limit_in_force"]).state == "60.0"
    assert state(ids["desired_tank_temperature"]).state == "10.0"
    # The S4 reference is A266's, not A237's.
    assert "desired_hot_water_flow_temperature" not in ids


@pytest.mark.parametrize("register_image", [{**HOLDING, 11252: 19200}])
async def test_no_value_reads_unknown(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """192.00 means the controller has no target - not 192 degrees."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    assert hass.states.get(ids["desired_flow_temperature"]).state == STATE_UNKNOWN


@pytest.mark.parametrize("application", ["a266_10_v03"])
@pytest.mark.parametrize("register_image", [{**HOLDING, 12253: 5500}])
async def test_the_a266_shows_its_hot_water_flow_target(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """A266 aims its hot water at S4, the flow; it has no tank reference."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    assert hass.states.get(ids["desired_hot_water_flow_temperature"]).state == "55.0"
    assert "desired_tank_temperature" not in ids
