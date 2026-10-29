"""Profile-specific installation settings and their Modbus behaviour."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from modbus_connection.mock import MockModbusConnection

from custom_components.ecl310.ecl310_modbus import PROFILES, Ecl310
from custom_components.ecl310.ecl310_modbus.exceptions import Ecl310ValueValidationError

from .conftest import ENTRY_DATA
from .test_integration import entity_ids, setup_entry


@pytest.mark.parametrize(
    ("application", "maximum"), [("a266_10_v03", 99), ("a237_1_v04", 100)]
)
async def test_parallel_operation_respects_each_application_domain(
    hass: HomeAssistant, connections: list[MockModbusConnection], maximum: int
) -> None:
    """The UI and the write use this controller's range, without affecting others."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    registry = er.async_get(hass)
    eid = ids["parallel_operation"]
    assert registry.async_get(eid).disabled_by is not None
    registry.async_update_entity(eid, disabled_by=None)
    await hass.async_block_till_done()
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(eid).attributes["max"] == 99
    unit = connections[-1].for_unit(ENTRY_DATA["unit_id"])
    if maximum == 99:
        original = unit.holding[11042]
        with pytest.raises(Ecl310ValueValidationError):
            await entry.runtime_data.coordinator.device.heating.write(
                "parallel_operation", 100
            )
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                "number", "set_value", {"entity_id": eid, "value": 100}, blocking=True
            )
        assert unit.holding[11042] == original
    else:
        await entry.runtime_data.coordinator.device.heating.write(
            "parallel_operation", 100
        )
        assert unit.holding[11042] == 100


def test_parallel_operation_domains_are_isolated_between_controllers() -> None:
    """A second controller cannot overwrite the first controller's bounds."""
    first = Ecl310(None, PROFILES["a266_10_v03"])
    second = Ecl310(None, PROFILES["a237_1_v04"])
    assert first.heating.metadata_for("parallel_operation").number.max_value == 99
    assert second.heating.metadata_for("parallel_operation").number.max_value == 100


@pytest.mark.parametrize("application", ["a367_1_v04"])
async def test_parallel_operation_absent_on_second_heating_circuit(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """A367 V04 does not offer 12043, so no second-circuit entity exists."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    assert "parallel_operation_circuit_1" in ids
    assert "parallel_operation_circuit_2" not in ids
    unit = connections[-1].for_unit(ENTRY_DATA["unit_id"])
    assert not any(
        event.address <= 12042 < event.address + event.count
        for event in unit.read_events
    )


@pytest.mark.parametrize("application", ["a266_10_v03"])
@pytest.mark.parametrize("refused_registers", [{11042}])
async def test_refused_parallel_operation_keeps_heating_operational(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """A refused optional register does not disable the thermostat."""
    entry = await setup_entry(hass, connections)
    coordinator = entry.runtime_data.coordinator
    assert "parallel_operation" in coordinator.refused("heating")
    assert "heating" not in coordinator.data.failed
    assert hass.states.get(entity_ids(hass, entry)["thermostat"]).state not in (
        "unavailable",
        "unknown",
    )


@pytest.mark.parametrize("application", ["a266_10_v03"])
async def test_building_factor_off_and_restored_value(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """OFF is not displayed as factor 9 and a previous factor can be restored."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    number_id = ids["building_factor"]
    switch_id = ids["building_factor_enabled"]
    registry = er.async_get(hass)
    for entity_id in (number_id, switch_id):
        assert registry.async_get(entity_id).disabled_by is not None
        registry.async_update_entity(entity_id, disabled_by=None)
    await hass.async_block_till_done()
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    unit = connections[-1].for_unit(ENTRY_DATA["unit_id"])
    assert unit.holding[11013] == 9
    assert hass.states.get(switch_id).state == "off"
    assert hass.states.get(number_id).state == "unknown"
    await hass.services.async_call(
        "number", "set_value", {"entity_id": number_id, "value": 25}, blocking=True
    )
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert unit.holding[11013] == 25
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": switch_id}, blocking=True
    )
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert unit.holding[11013] == 9
    assert hass.states.get(number_id).state == "unknown"
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": switch_id}, blocking=True
    )
    assert connections[-1].for_unit(ENTRY_DATA["unit_id"]).holding[11013] == 25


@pytest.mark.parametrize("application", ["a266_10_v03"])
@pytest.mark.parametrize(
    "setting",
    [
        ("auto_saving", 11010, -30, -15),
        ("heat_up_boost", 11011, 0, 20),
        ("ramp_time", 11012, 0, 15),
    ],
)
async def test_optimisation_setting_can_represent_and_restore_off(
    hass: HomeAssistant,
    connections: list[MockModbusConnection],
    setting: tuple[str, int, int, int],
) -> None:
    """The OFF sentinel is distinct from a numeric value and remains writable."""
    field, address, off, active = setting
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    registry = er.async_get(hass)
    number_id, switch_id = ids[field], ids[f"{field}_enabled"]
    for entity_id in (number_id, switch_id):
        assert registry.async_get(entity_id).disabled_by is not None
        registry.async_update_entity(entity_id, disabled_by=None)
    await hass.async_block_till_done()
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await hass.services.async_call(
        "number", "set_value", {"entity_id": number_id, "value": active}, blocking=True
    )
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": switch_id}, blocking=True
    )
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    unit = connections[-1].for_unit(ENTRY_DATA["unit_id"])
    assert unit.holding[address] == (off & 0xFFFF)
    assert hass.states.get(number_id).state == "unknown"
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": switch_id}, blocking=True
    )
    assert unit.holding[address] == (active & 0xFFFF)


@pytest.mark.parametrize("application", ["a266_10_v03"])
async def test_optimised_stop_writes_its_own_switch(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """Pre-stop follows PNU 11026 and is disabled on first installation."""
    entry = await setup_entry(hass, connections)
    eid = entity_ids(hass, entry)["optimised_stop"]
    registry = er.async_get(hass)
    assert registry.async_get(eid).disabled_by is not None
    registry.async_update_entity(eid, disabled_by=None)
    await hass.async_block_till_done()
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(eid).attributes["pnu"] == 11026
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": eid}, blocking=True
    )
    assert connections[-1].for_unit(ENTRY_DATA["unit_id"]).holding[11025] == 1


@pytest.mark.parametrize(
    ("application", "full_mode"), [("a237_1_v04", "on"), ("a266_10_v03", "absent")]
)
async def test_parallel_operation_modes_represent_sentinels(
    hass: HomeAssistant, connections: list[MockModbusConnection], full_mode: str
) -> None:
    """Zero is OFF, 1-99 is conditional, and 100 is ON only where supported."""
    has_on = full_mode == "on"
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    registry = er.async_get(hass)
    mode_id, threshold_id = ids["parallel_operation_mode"], ids["parallel_operation"]
    for eid in (mode_id, threshold_id):
        registry.async_update_entity(eid, disabled_by=None)
    await hass.async_block_till_done()
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    options = hass.states.get(mode_id).attributes["options"]
    assert options == (
        ["off", "conditional", "on"] if has_on else ["off", "conditional"]
    )
    unit = connections[-1].for_unit(ENTRY_DATA["unit_id"])
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": mode_id, "option": "off"},
        blocking=True,
    )
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert unit.holding[11042] == 0
    assert hass.states.get(threshold_id).state == "unknown"
    await hass.services.async_call(
        "number", "set_value", {"entity_id": threshold_id, "value": 25}, blocking=True
    )
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert unit.holding[11042] == 25
    assert hass.states.get(mode_id).state == "conditional"
    if has_on:
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": mode_id, "option": "on"},
            blocking=True,
        )
        await entry.runtime_data.coordinator.async_refresh()
        await hass.async_block_till_done()
        assert unit.holding[11042] == 100
        assert hass.states.get(threshold_id).state == "unknown"


@pytest.mark.parametrize("application", sorted(PROFILES))
async def test_optimisation_settings_follow_every_profile(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """Only documented circuit settings are registered on every profile."""
    entry = await setup_entry(hass, connections)
    device = entry.runtime_data.coordinator.device
    ids = entity_ids(hass, entry)
    registry = er.async_get(hass)
    for circuit in device.circuits:
        if circuit.kind != "heating":
            continue
        for name, suffix in (
            ("auto_saving", 11),
            ("heat_up_boost", 12),
            ("ramp_time", 13),
            ("building_factor", 14),
            ("optimised_stop", 26),
            ("parallel_operation", 43),
        ):
            key = name + (f"_circuit_{circuit.number}" if circuit.numbered else "")
            pnu = 10000 + 1000 * circuit.number + suffix
            if pnu in device.application.parameters:
                assert key in ids
                assert registry.async_get(ids[key]).disabled_by is not None
            else:
                assert key not in ids
