"""The one-off hot water boost against the captured controller."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import Context, HomeAssistant
from modbus_connection.mock import MockModbusConnection
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockUser,
    async_capture_events,
)

from .conftest import ENTRY_DATA, HOLDING
from .test_integration import entity_ids, setup_entry

MODE = 4201  # hot water operating mode: 1 scheduled, 2 comfort, 4 frost
SETPOINT = 12189  # hot water setpoint in tenths of a degree
STORAGE = 10205  # S6 in hundredths of a degree
EVENT = "ecl310_hot_water_boost_finished"


async def _poll(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()


def _unit(connections: list[MockModbusConnection]) -> Any:
    return connections[-1].for_unit(ENTRY_DATA["unit_id"])


async def _switch(
    hass: HomeAssistant, entity_id: str, *, on: bool, context: Context | None = None
) -> None:
    await hass.services.async_call(
        "switch",
        "turn_on" if on else "turn_off",
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
        context=context,
    )
    await hass.async_block_till_done()


async def test_boost_heats_to_the_setpoint_and_goes_back(
    hass: HomeAssistant,
    connections: list[MockModbusConnection],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Comfort until S6 reaches the setpoint, then the weekly program again."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    unit = _unit(connections)
    events = async_capture_events(hass, EVENT)
    unit.holding[SETPOINT] = 500  # 50 °C, tank at 45.36 °C
    await _poll(hass, entry)

    await _switch(hass, ids["hot_water_boost"], on=True)
    assert unit.holding[MODE] == 2
    switch = hass.states.get(ids["hot_water_boost"])
    assert switch.state == "on"
    assert switch.attributes["start_temperature"] == 45.4
    assert switch.attributes["previous_mode"] == "scheduled"
    assert hass.states.get(ids["hot_water_boost_start_temperature"]).state == "45.4"

    # Ten minutes later the tank gained two degrees: 0.2 K/min, 23 min to go.
    freezer.tick(timedelta(minutes=10))
    unit.holding[STORAGE] = 4736
    await _poll(hass, entry)
    switch = hass.states.get(ids["hot_water_boost"])
    assert switch.attributes["rate"] == 0.2
    assert float(hass.states.get(ids["hot_water_boost_duration"]).state) == 10
    end = hass.states.get(ids["hot_water_boost_estimated_end"]).state
    assert end not in ("unknown", "unavailable")

    unit.holding[STORAGE] = 5010
    await _poll(hass, entry)
    assert unit.holding[MODE] == 1
    assert hass.states.get(ids["hot_water_boost"]).state == "off"
    assert hass.states.get(ids["hot_water_boost_start_temperature"]).state == "unknown"
    assert len(events) == 1
    data = events[0].data
    assert data["result"] == "reached"
    assert data["start_temperature"] == 45.4
    assert data["end_temperature"] == 50.1
    assert data["duration_minutes"] == 10.0
    assert data["target"] == 50.0


async def test_raising_the_setpoint_starts_a_boost_when_wanted(
    hass: HomeAssistant,
    connections: list[MockModbusConnection],
    hass_admin_user: MockUser,
) -> None:
    """With "boost on raise", a setpoint above the tank starts one - and says who."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    unit = _unit(connections)
    events = async_capture_events(hass, EVENT)

    async def set_temperature(value: float) -> None:
        await hass.services.async_call(
            "water_heater",
            "set_temperature",
            {ATTR_ENTITY_ID: ids["water_heater"], "temperature": value},
            blocking=True,
            context=Context(user_id=hass_admin_user.id),
        )
        await hass.async_block_till_done()

    await set_temperature(52)  # setting off: nothing happens
    assert unit.holding[MODE] == 1
    assert hass.states.get(ids["hot_water_boost"]).state == "off"

    await _switch(hass, ids["hot_water_boost_on_raise"], on=True)
    await set_temperature(46)  # within a degree of the tank: no boost
    assert unit.holding[MODE] == 1
    await set_temperature(55)
    assert unit.holding[MODE] == 2
    assert hass.states.get(ids["hot_water_boost"]).state == "on"

    await _switch(hass, ids["hot_water_boost"], on=False)
    assert unit.holding[MODE] == 1
    assert events[0].data["result"] == "cancelled"
    assert events[0].data["user_id"] == hass_admin_user.id


async def test_a_mode_chosen_meanwhile_ends_the_boost_and_stays(
    hass: HomeAssistant,
    connections: list[MockModbusConnection],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Someone choosing frost protection (absence) wins over the boost."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    unit = _unit(connections)
    events = async_capture_events(hass, EVENT)
    unit.holding[SETPOINT] = 550
    await _poll(hass, entry)
    await _switch(hass, ids["hot_water_boost"], on=True)

    unit.holding[MODE] = 4
    freezer.tick(timedelta(minutes=2))
    await _poll(hass, entry)
    assert unit.holding[MODE] == 4
    assert hass.states.get(ids["hot_water_boost"]).state == "off"
    assert events[0].data["result"] == "mode_changed"


async def test_a_boost_gives_up_after_three_hours(
    hass: HomeAssistant,
    connections: list[MockModbusConnection],
    freezer: FrozenDateTimeFactory,
) -> None:
    """A tank that never gets there does not stay in comfort for ever."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    unit = _unit(connections)
    events = async_capture_events(hass, EVENT)
    unit.holding[SETPOINT] = 650
    await _poll(hass, entry)
    await _switch(hass, ids["hot_water_boost"], on=True)

    freezer.tick(timedelta(hours=3, minutes=1))
    await _poll(hass, entry)
    assert unit.holding[MODE] == 1
    assert events[0].data["result"] == "timeout"


async def test_lowering_the_setpoint_below_the_tank_finishes_the_boost(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """The boost follows the setpoint while it runs."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    unit = _unit(connections)
    events = async_capture_events(hass, EVENT)
    unit.holding[SETPOINT] = 550
    await _poll(hass, entry)
    await _switch(hass, ids["hot_water_boost"], on=True)

    await hass.services.async_call(
        "water_heater",
        "set_temperature",
        {ATTR_ENTITY_ID: ids["water_heater"], "temperature": 45},
        blocking=True,
    )
    await _poll(hass, entry)
    assert unit.holding[MODE] == 1
    assert events[0].data["result"] == "reached"


async def test_a_running_boost_survives_a_reload(
    hass: HomeAssistant,
    connections: list[MockModbusConnection],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stored, and picked up again while the controller is still in comfort."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    unit = _unit(connections)
    unit.holding[SETPOINT] = 550
    await _poll(hass, entry)
    await _switch(hass, ids["hot_water_boost"], on=True)
    await _switch(hass, ids["hot_water_boost_on_raise"], on=True)

    # A reload opens a fresh mock controller: seed it as the real one would be.
    monkeypatch.setitem(HOLDING, MODE, 2)
    monkeypatch.setitem(HOLDING, SETPOINT, 550)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(ids["hot_water_boost"]).state == "on"
    assert hass.states.get(ids["hot_water_boost_on_raise"]).state == "on"
    assert entry.runtime_data.boost.session.previous_mode.name == "SCHEDULED"

    # Back from a restart in another mode: the boost is over, not resumed.
    monkeypatch.setitem(HOLDING, MODE, 1)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(ids["hot_water_boost"]).state == "off"


async def test_writing_the_same_setpoint_is_no_raise(
    hass: HomeAssistant,
    connections: list[MockModbusConnection],
    hass_admin_user: MockUser,
) -> None:
    """An automation setting 40 C where it already is starts no boost.

    2026-10-18: the tank had cooled to 36.5 C overnight, the morning
    automation wrote the unchanged 40 C, and a boost ran.
    """
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    unit = _unit(connections)
    unit.holding[SETPOINT] = 400
    unit.holding[STORAGE] = 3650
    await _poll(hass, entry)
    await _switch(hass, ids["hot_water_boost_on_raise"], on=True)

    await hass.services.async_call(
        "water_heater",
        "set_temperature",
        {ATTR_ENTITY_ID: ids["water_heater"], "temperature": 40},
        blocking=True,
        context=Context(user_id=hass_admin_user.id),
    )
    await hass.async_block_till_done()
    assert unit.holding[MODE] == 1
    assert hass.states.get(ids["hot_water_boost"]).state == "off"


async def test_frost_protection_is_not_left_by_a_raise(
    hass: HomeAssistant,
    connections: list[MockModbusConnection],
    hass_admin_user: MockUser,
) -> None:
    """Frost protection (absence) is a deliberate off: only a hand boost leaves it."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    unit = _unit(connections)
    unit.holding[MODE] = 4
    unit.holding[SETPOINT] = 400
    await _poll(hass, entry)
    await _switch(hass, ids["hot_water_boost_on_raise"], on=True)

    await hass.services.async_call(
        "water_heater",
        "set_temperature",
        {ATTR_ENTITY_ID: ids["water_heater"], "temperature": 55},
        blocking=True,
        context=Context(user_id=hass_admin_user.id),
    )
    await hass.async_block_till_done()
    assert unit.holding[MODE] == 4
    assert hass.states.get(ids["hot_water_boost"]).state == "off"

    await _switch(hass, ids["hot_water_boost"], on=True)  # by hand: allowed
    assert unit.holding[MODE] == 2
