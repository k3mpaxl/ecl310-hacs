"""Alarm masks and contexts are read without guessing application meanings."""

import pytest
from homeassistant.core import HomeAssistant
from modbus_connection.mock import MockModbusConnection

from .conftest import ENTRY_DATA
from .test_integration import entity_ids, setup_entry


@pytest.mark.parametrize("application", ["a266_10_v03"])
async def test_alarm_masks_and_context(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """Verify the alarm diagnostic against simulated register values."""
    entry = await setup_entry(hass, connections)
    unit = connections[-1].for_unit(ENTRY_DATA["unit_id"])
    unit.holding[1024] = 1  # PNU 1025, ID 1
    unit.holding[1023] = 2  # PNU 1024, ID 18
    unit.holding[1056] = 7  # PNU 1057, ID 18
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get(entity_ids(hass, entry)["active_alarms"])
    assert state.state == "2"
    assert state.attributes["alarm_ids"] == [1, 18]
    assert state.attributes["contexts"]["18"] == 7
    unit.holding[1023] = unit.holding[1024] = 0
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(state.entity_id).state == "0"


@pytest.mark.parametrize("application", ["a266_10_v03"])
@pytest.mark.parametrize("refused_registers", [{1023}])
async def test_partial_alarm_mask_never_reports_all_clear(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """Verify the alarm diagnostic against simulated register values."""
    entry = await setup_entry(hass, connections)
    state = hass.states.get(entity_ids(hass, entry)["active_alarms"])
    assert state.state == "unavailable"
    assert hass.states.get(entity_ids(hass, entry)["thermostat"]).state not in (
        "unavailable",
        "unknown",
    )
