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


@pytest.mark.parametrize("application", ["a266_10_v03"])
async def test_a266_control_valve_and_pump_threshold_are_circuit_specific(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """A266 exposes the hot-water valve and its 80 C pump threshold on circuit 2."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    registry = er.async_get(hass)
    motor_id = ids["hot_water_valve_running_time"]
    threshold_id = ids["hot_water_pump_heat_threshold"]
    actuator_id = ids["hot_water_actuator_type"]
    for eid in (motor_id, threshold_id, actuator_id):
        assert registry.async_get(eid).disabled_by is not None
        registry.async_update_entity(eid, disabled_by=None)
    await hass.async_block_till_done()
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(motor_id).attributes["pnu"] == 12186
    assert hass.states.get(threshold_id).attributes["max"] == 80
    assert hass.states.get(threshold_id).attributes["pnu"] == 12078
    assert hass.states.get(actuator_id).attributes["pnu"] == 12024
    await hass.services.async_call(
        "number", "set_value", {"entity_id": motor_id, "value": 75}, blocking=True
    )
    assert connections[-1].for_unit(ENTRY_DATA["unit_id"]).holding[12185] == 75


@pytest.mark.parametrize("application", ["a266_10_v03"])
async def test_actuator_select_maps_documented_modes(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """The A266 hot-water actuator select writes 0 for ABV and 1 for motor."""
    entry = await setup_entry(hass, connections)
    eid = entity_ids(hass, entry)["hot_water_actuator_type"]
    registry = er.async_get(hass)
    registry.async_update_entity(eid, disabled_by=None)
    await hass.async_block_till_done()
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    unit = connections[-1].for_unit(ENTRY_DATA["unit_id"])
    for option, raw in (("m_abv", 0), ("m_3_point", 1)):
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": eid, "option": option},
            blocking=True,
        )
        assert unit.holding[12023] == raw


@pytest.mark.parametrize("application", ["a266_10_v03"])
async def test_seasonal_filter_can_reach_300_and_restore_off(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """The 16-bit summer filter reaches 300 and zero is an OFF sentinel."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    registry = er.async_get(hass)
    for key in ("summer_filter", "summer_filter_enabled"):
        registry.async_update_entity(ids[key], disabled_by=None)
    await hass.async_block_till_done()
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": ids["summer_filter"], "value": 300},
        blocking=True,
    )
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    unit = connections[-1].for_unit(ENTRY_DATA["unit_id"])
    assert unit.holding[11394] == 300
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": ids["summer_filter_enabled"]}, blocking=True
    )
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert unit.holding[11394] == 0
    assert hass.states.get(ids["summer_filter"]).state == "unknown"
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": ids["summer_filter_enabled"]}, blocking=True
    )
    assert unit.holding[11394] == 300


@pytest.mark.parametrize("application", ["a337_2_v02"])
async def test_absent_seasonal_settings_are_not_registered(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """A337 V02 has no new summer/winter filter or date settings."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    for key in (
        "summer_start_month",
        "summer_start_day",
        "summer_filter",
        "winter_cut_off",
        "winter_filter",
    ):
        assert key not in ids


@pytest.mark.parametrize("application", ["a266_10_v03"])
@pytest.mark.parametrize(
    "setting",
    [
        ("hot_water_pump_frost_threshold", 12076, -11, 2),
        ("hot_water_valve_motor_protection", 12173, 9, 20),
    ],
)
async def test_circuit_installer_off_values_round_trip(
    hass: HomeAssistant,
    connections: list[MockModbusConnection],
    setting: tuple[str, int, int, int],
) -> None:
    """Negative and motor OFF sentinels round-trip on A266 circuit 2."""
    name, address, off, active = setting
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    registry = er.async_get(hass)
    for key in (name, name + "_enabled"):
        registry.async_update_entity(ids[key], disabled_by=None)
    await hass.async_block_till_done()
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await hass.services.async_call(
        "number", "set_value", {"entity_id": ids[name], "value": active}, blocking=True
    )
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": ids[name + "_enabled"]}, blocking=True
    )
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    unit = connections[-1].for_unit(ENTRY_DATA["unit_id"])
    assert unit.holding[address] == (off & 0xFFFF)
    assert hass.states.get(ids[name]).state == "unknown"
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": ids[name + "_enabled"]}, blocking=True
    )
    assert unit.holding[address] == active


@pytest.mark.parametrize("application", sorted(PROFILES))
async def test_valve_and_pump_settings_follow_supported_profiles(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """Both circuit kinds expose only installer PNUs actually in their profile."""
    entry = await setup_entry(hass, connections)
    device = entry.runtime_data.coordinator.device
    ids = entity_ids(hass, entry)
    registry = er.async_get(hass)
    for circuit in device.circuits:
        prefix = "hot_water_" if circuit.kind == "hot_water" else ""
        suffix = f"_circuit_{circuit.number}" if circuit.numbered else ""
        for name, offset in (
            ("pump_exercise", 22),
            ("valve_exercise", 23),
            ("actuator_type", 24),
            ("pump_frost_threshold", 77),
            ("pump_heat_threshold", 78),
            ("valve_motor_protection", 174),
            ("valve_proportional_band", 184),
            ("valve_integral_time", 185),
            ("valve_running_time", 186),
            ("valve_neutral_zone", 187),
            ("valve_minimum_pulse", 189),
        ):
            key = prefix + name + suffix
            pnu = 10000 + circuit.number * 1000 + offset
            if pnu not in device.application.parameters:
                assert key not in ids
                continue
            assert registry.async_get(ids[key]).disabled_by is not None
            component = getattr(device, circuit.component)
            assert component.metadata_for(name).parameter_id == pnu


@pytest.mark.parametrize("application", ["a266_10_v03"])
async def test_installer_registers_are_polled_on_a_slow_cadence(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """Routine refreshes read climate but omit unchanged installer registers."""
    entry = await setup_entry(hass, connections)
    coordinator = entry.runtime_data.coordinator
    unit = connections[-1].for_unit(ENTRY_DATA["unit_id"])
    unit.read_events.clear()
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert any(
        event.address <= 11179 < event.address + event.count
        for event in unit.read_events
    )
    for addr in (11042, 11076, 11185, 11394):
        assert not any(
            event.address <= addr < event.address + event.count
            for event in unit.read_events
        )
    assert "heating" not in coordinator.data.failed


@pytest.mark.parametrize("application", ["a266_10_v03"])
async def test_slow_setting_reads_periodically_and_after_write(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """External changes appear on the slow cycle; writes trigger readback sooner."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    eid = ids["valve_running_time"]
    registry = er.async_get(hass)
    registry.async_update_entity(eid, disabled_by=None)
    await hass.async_block_till_done()
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data.coordinator
    unit = connections[-1].for_unit(ENTRY_DATA["unit_id"])
    original = hass.states.get(eid).state
    unit.holding[11185] = 77
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == original
    for _ in range(9):
        await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == "77"
    await hass.services.async_call(
        "number", "set_value", {"entity_id": eid, "value": 60}, blocking=True
    )
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == "60"


@pytest.mark.parametrize("application", ["a266_10_v03"])
async def test_a266_alarm_input_and_flow_settings(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """A266 exposes its flow alarm and documented input contact polarity."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    assert "alarm_flow_upper_difference" not in ids
    registry = er.async_get(hass)
    for key in (
        "alarm_max_flow",
        "alarm_flow_delay_seconds",
        "alarm_input_polarity",
        "alarm_input_delay",
    ):
        assert registry.async_get(ids[key]).disabled_by is not None
        registry.async_update_entity(ids[key], disabled_by=None)
    await hass.async_block_till_done()
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(ids["alarm_max_flow"]).attributes["pnu"] == 11079
    assert hass.states.get(ids["alarm_input_polarity"]).attributes["pnu"] == 11636
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": ids["alarm_input_polarity"], "option": "closed"},
        blocking=True,
    )
    unit = connections[-1].for_unit(ENTRY_DATA["unit_id"])
    assert unit.holding[11635] == 0
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": ids["alarm_input_polarity"], "option": "open"},
        blocking=True,
    )
    assert unit.holding[11635] == 1


@pytest.mark.parametrize("application", ["a237_1_v04"])
async def test_a237_alarm_difference_off_is_not_zero_kelvin(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """The upper difference OFF sentinel is shown separately from a threshold."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    assert "alarm_max_flow" not in ids
    registry = er.async_get(hass)
    for key in ("alarm_flow_upper_difference", "alarm_flow_upper_difference_enabled"):
        registry.async_update_entity(ids[key], disabled_by=None)
    await hass.async_block_till_done()
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": ids["alarm_flow_upper_difference"], "value": 5},
        blocking=True,
    )
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": ids["alarm_flow_upper_difference_enabled"]},
        blocking=True,
    )
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert connections[-1].for_unit(ENTRY_DATA["unit_id"]).holding[11146] == 0
    assert hass.states.get(ids["alarm_flow_upper_difference"]).state == "unknown"


@pytest.mark.parametrize("application", sorted(PROFILES))
async def test_alarm_settings_follow_each_supported_profile(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """Alarm settings and absence of x617 follow each profile and heating circuit."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    device = entry.runtime_data.coordinator.device
    registry = er.async_get(hass)
    for circuit in device.circuits:
        if circuit.kind != "heating":
            continue
        suffix = f"_circuit_{circuit.number}" if circuit.numbered else ""
        for name, offset in (
            ("alarm_max_flow", 79),
            ("alarm_flow_delay_seconds", 80),
            ("alarm_flow_upper_difference", 147),
            ("alarm_flow_lower_difference", 148),
            ("alarm_flow_difference_delay", 149),
            ("alarm_flow_monitor_threshold", 150),
            ("alarm_input_polarity", 636),
            ("alarm_input_delay", 637),
        ):
            key = name + suffix
            pnu = 10000 + 1000 * circuit.number + offset
            if pnu in device.application.parameters:
                assert registry.async_get(ids[key]).disabled_by is not None
                assert (
                    getattr(device, circuit.component).metadata_for(name).parameter_id
                    == pnu
                )
            else:
                assert key not in ids
        assert 10000 + 1000 * circuit.number + 617 not in device.application.parameters
