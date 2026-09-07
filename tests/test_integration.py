"""Run the integration in a real Home Assistant against the captured device."""

from __future__ import annotations

import pytest
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from modbus_connection.mock import MockModbusConnection
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import DOMAIN, ENTRY_DATA


def entity_ids(hass: HomeAssistant, entry: MockConfigEntry) -> dict[str, str]:
    """Map each entity's key back to the entity id it was registered under."""
    registry = er.async_get(hass)
    return {
        entity.unique_id.removeprefix(f"{entry.entry_id}_"): entity.entity_id
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
    }


async def setup_entry(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> MockConfigEntry:
    """Load a config entry pointing at the seeded controller."""
    entry = MockConfigEntry(
        domain=DOMAIN, data=ENTRY_DATA, unique_id="192.168.1.100:502:1"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_flow_reads_the_model_and_loads(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """The flow probes the controller, names the entry after it, and sets up."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], dict(ENTRY_DATA)
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Danfoss ECL Comfort 310"
    assert result["result"].state is ConfigEntryState.LOADED


async def test_the_entities_carry_the_controllers_values(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """Every platform decodes the captured register image."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)

    assert hass.states.get(ids["outdoor_temperature"]).state == "30.22"
    assert hass.states.get(ids["flow_temperature"]).state == "55.36"
    assert hass.states.get(ids["summer_cut_off"]).state == "12"
    assert hass.states.get(ids["pump_off_in_setback"]).state == "on"

    thermostat = hass.states.get(ids["thermostat"])
    assert thermostat.state == "off"  # the circuit is in frost protection
    assert thermostat.attributes["preset_mode"] == "frost_protection"
    assert thermostat.attributes["temperature"] == 22.0

    water = hass.states.get(ids["water_heater"])
    assert water.attributes["temperature"] == 40.0
    assert water.attributes["current_temperature"] == 45.4  # rounded for display
    assert water.attributes["operation_mode"] == "scheduled"


async def test_the_controller_is_a_device_with_two_sub_devices(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """The circuits hang off the controller, which exists before they do."""
    entry = await setup_entry(hass, connections)
    registry = dr.async_get(hass)

    controller = registry.async_get_device({(DOMAIN, entry.entry_id)})
    assert controller is not None
    assert controller.manufacturer == "Danfoss"

    for sub_id, name in (("heating", "Heating circuit"), ("hot_water", "Hot water")):
        device = registry.async_get_device({(DOMAIN, f"{entry.entry_id}_{sub_id}")})
        assert device is not None
        assert device.via_device_id == controller.id
        assert device.name == name


async def test_writes_reach_the_controller(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """Setpoint and mode changes end up in the registers they belong to."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    unit = connections[-1].for_unit(ENTRY_DATA["unit_id"])

    await hass.services.async_call(
        "water_heater",
        "set_temperature",
        {"entity_id": ids["water_heater"], "temperature": 55},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert await unit.read_holding_registers(12189, 1) == [550]

    await hass.services.async_call(
        "water_heater",
        "set_operation_mode",
        {"entity_id": ids["water_heater"], "operation_mode": "comfort"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert await unit.read_holding_registers(4201, 1) == [2]

    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": ids["thermostat"], "hvac_mode": "auto"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert await unit.read_holding_registers(4200, 1) == [1]

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": ids["disinfection_temperature"], "value": 65},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert await unit.read_holding_registers(12124, 1) == [65]


async def test_unloading_closes_the_link(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """The entry owns its connection, so unloading has to close it."""
    entry = await setup_entry(hass, connections)
    connection = connections[-1]
    assert connection.connected is False or connection.connected is True

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_forcing_a_pump_writes_the_override_register(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """The state register is refused by the controller; the override is not.

    Relay 3 is the circulation pump on A237.1. Its state lives at 4007 and its
    override at 4067, and only the second one may be written.
    """
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    unit = connections[-1].for_unit(ENTRY_DATA["unit_id"])

    assert hass.states.get(ids["circulation_pump_override"]).state == "auto"

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": ids["circulation_pump_override"], "option": "on"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert await unit.read_holding_registers(4067, 1) == [2]
    assert hass.states.get(ids["circulation_pump_override"]).state == "on"
    assert hass.states.get(ids["circulation_pump"]).state == "on"  # it followed

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": ids["circulation_pump_override"], "option": "auto"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert await unit.read_holding_registers(4067, 1) == [0]


async def test_a_pump_reports_its_state_and_is_controlled_separately(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """What a pump is doing is a sensor; what it is told to do is a select."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)

    for key in ("heating_pump", "storage_charge_pump", "circulation_pump"):
        assert ids[key].startswith("binary_sensor."), key
        assert ids[f"{key}_override"].startswith("select."), key
    for key in ("relay_4", "relay_5", "relay_6", "triac_1", "triac_6"):
        assert ids[key].startswith("binary_sensor."), key

    # Nothing was running when the reference image was captured.
    assert hass.states.get(ids["heating_pump"]).state == "off"
    assert hass.states.get(ids["circulation_pump"]).state == "off"


async def test_the_sub_devices_are_named_in_the_users_language(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """A German profile gets German device names, not English ones."""
    hass.config.language = "de"
    entry = await setup_entry(hass, connections)
    registry = dr.async_get(hass)

    for sub_id, name in (("heating", "Heizkreis"), ("hot_water", "Warmwasser")):
        device = registry.async_get_device({(DOMAIN, f"{entry.entry_id}_{sub_id}")})
        assert device is not None
        assert device.name == name


async def test_the_weekly_program_is_read_and_written(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """Each period boundary is one entity over one register."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    unit = connections[-1].for_unit(ENTRY_DATA["unit_id"])

    # Monday's first heating period, register 3109 (start) and 3110 (stop).
    start = ids["heating_schedule_monday_p1_start"]
    assert hass.states.get(start).state == "06:00:00"

    await hass.services.async_call(
        "time",
        "set_value",
        {"entity_id": start, "time": "05:30:00"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert await unit.read_holding_registers(3109, 1) == [530]
    assert hass.states.get(start).state == "05:30:00"


async def test_only_the_first_period_is_enabled_by_default(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """The controller stores an unused period as a zero-length one."""
    entry = await setup_entry(hass, connections)
    registry = er.async_get(hass)
    entries = {
        entity.unique_id.removeprefix(f"{entry.entry_id}_"): entity
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    for circuit in ("heating_schedule", "hot_water_schedule"):
        assert entries[f"{circuit}_monday_p1_start"].disabled_by is None
        assert (
            entries[f"{circuit}_monday_p2_start"].disabled_by
            is er.RegistryEntryDisabler.INTEGRATION
        )


async def test_the_schedules_stay_out_of_most_polls(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """They are fourteen reads for values only an operator changes."""
    entry = await setup_entry(hass, connections)
    unit = connections[-1].for_unit(ENTRY_DATA["unit_id"])

    schedule_reads = [e for e in unit.read_events if 3100 <= e.address < 3300]
    assert len(schedule_reads) == 14  # the first poll takes them

    unit.read_events.clear()
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert not [e for e in unit.read_events if 3100 <= e.address < 3300]


async def test_the_anti_bacteria_run(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """A bit mask of weekdays and a start counted in half hours."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    unit = connections[-1].for_unit(ENTRY_DATA["unit_id"])

    assert hass.states.get(ids["disinfection_saturday"]).state == "on"
    assert hass.states.get(ids["disinfection_monday"]).state == "off"
    assert hass.states.get(ids["disinfection_start"]).state == "05:00:00"

    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": ids["disinfection_monday"]},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert await unit.read_holding_registers(12121, 1) == [0b0100001]

    # 04:45 falls in the 04:30 slot; the controller counts half hours.
    await hass.services.async_call(
        "time",
        "set_value",
        {"entity_id": ids["disinfection_start"], "time": "04:45:00"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert await unit.read_holding_registers(12122, 1) == [9]


async def test_the_heat_curve_and_its_points(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """The slope and the six points the ECL calls Y1 to Y6."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    unit = connections[-1].for_unit(ENTRY_DATA["unit_id"])

    assert hass.states.get(ids["heat_curve"]).state == "1.5"
    assert hass.states.get(ids["curve_at_minus_30"]).state == "100"

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": ids["curve_at_0"], "value": 58},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert await unit.read_holding_registers(11402, 1) == [58]


async def test_every_entity_has_a_unique_id_of_its_own(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """Two entities sharing a unique id means Home Assistant drops one.

    It does it quietly - an error in the log and a missing entity - which is
    how both weekly programs once ended up as one. The two schedules describe
    the same 42 boundaries, so their keys have to carry the circuit.
    """
    entry = await setup_entry(hass, connections)
    entries = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)

    unique_ids = [entity.unique_id for entity in entries]
    assert len(unique_ids) == len(set(unique_ids))

    # 42 boundaries per circuit, plus the anti-bacteria start.
    assert len([e for e in entries if e.domain == "time"]) == 85
    for component in ("heating_schedule", "hot_water_schedule"):
        boundaries = [e for e in entries if f"_{component}_" in e.unique_id]
        assert len(boundaries) == 42, component


async def test_manual_mode_is_reported_but_never_offered(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """Manual disables the regulation and the frost protection at the ECL.

    It also refuses the output override this integration writes, and takes
    every circuit with it - so it is readable but not settable.
    """
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)

    thermostat = hass.states.get(ids["thermostat"])
    assert "manual" not in thermostat.attributes["preset_modes"]
    assert "scheduled" in thermostat.attributes["preset_modes"]
    assert (
        "manual"
        not in hass.states.get(ids["water_heater"]).attributes["operation_list"]
    )

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "climate",
            "set_preset_mode",
            {"entity_id": ids["thermostat"], "preset_mode": "manual"},
            blocking=True,
        )


async def test_a_controller_in_manual_says_so(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """The mode is still decoded, and joins the list while it is the truth."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    unit = connections[-1].for_unit(ENTRY_DATA["unit_id"])

    unit.holding[4200] = 0  # the heating circuit's mode register: manual
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    thermostat = hass.states.get(ids["thermostat"])
    assert thermostat.attributes["preset_mode"] == "manual"
    assert "manual" in thermostat.attributes["preset_modes"]
