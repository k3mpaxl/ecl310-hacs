"""A367.1 V04 (issue 38): two heating circuits and hot water on circuit 3.

Simulated from the captured A237.1 image, refusing what A367.1 lacks and
reporting A367.1 V04 as its application. Everything below follows from the
Danfoss report by rule - circuit kinds, sensor roles, the circuits' parameters
- and from the ECL Tool's A367.1 drawing for the pumps and valves.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from modbus_connection.mock import MockModbusConnection

from custom_components.ecl310.ecl310_modbus import PROFILES, Ecl310, HotWater

from .conftest import DOMAIN
from .test_integration import entity_ids, setup_entry

A367 = "a367_1_v04"

pytestmark = pytest.mark.parametrize("application", [A367])

#: What the A367.1 controller of issue 38 refused under 0.12.0, which read the
#: A237 layout: exactly circuit 2's hot water parameters - A367.1 keeps its hot
#: water on circuit 3 (the owner's Home Assistant log, 2026-10-18).
REFUSED_ON_THE_OWNERS_CONTROLLER = {
    12030,
    12076,
    12122,
    12123,
    12124,
    12125,
    12152,
    12190,
    12191,
    12193,
    12194,
    12195,
    12256,
}


def test_the_profile_predicts_what_the_owners_controller_refused(
    application: str,
) -> None:
    """Of the A237 hot water parameters, A367.1 lacks exactly those refused."""
    profile = PROFILES[application]
    read_by_0_12 = {
        field.ecl_metadata.parameter_id
        for field in HotWater.declared_fields.values()
        if field.ecl_metadata.parameter_id is not None
    }
    lacking = {pnu for pnu in read_by_0_12 if not profile.has(pnu)}
    assert lacking == REFUSED_ON_THE_OWNERS_CONTROLLER


def test_the_register_map_matches_the_owners_own_version(application: str) -> None:
    """The owner moved hot water by hand: 13xxx, mode 4202, program 3310.

    His modified 0.9.0 (issue 38) controls his installation with these
    registers; the derived layout arrives at the same ones.
    """
    device = Ecl310(None, application=PROFILES[application])  # type: ignore[arg-type]
    water = type(device.hot_water).declared_fields
    assert water["mode"].address == 4202
    assert water["state"].address == 4212
    assert water["setpoint"].address == 13189
    assert water["disinfection_temperature"].address == 13124
    program = type(device.hot_water_schedule).declared_fields
    assert program["monday_p1_start"].address == 3309


async def test_each_circuit_is_a_device_named_by_its_number(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """Two heating circuits are told apart by number; hot water needs none."""
    hass.config.language = "de"
    entry = await setup_entry(hass, connections)
    assert entry.data["application"] == A367
    registry = dr.async_get(hass)
    names = {
        sub: registry.async_get_device_by_identifier(
            (DOMAIN, f"{entry.entry_id}_{sub}"), entry.entry_id
        ).name
        for sub in ("heating_1", "heating_2", "hot_water")
    }
    assert names == {
        "heating_1": "Heizkreis 1",
        "heating_2": "Heizkreis 2",
        "hot_water": "Warmwasser",
    }


async def test_a_function_reads_its_own_circuit(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """The summer cut-off is 11179 on circuit 1 and 12179 on circuit 2."""
    hass.config.language = "de"
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    state = hass.states.get

    first = state(ids["summer_cut_off_circuit_1"])
    second = state(ids["summer_cut_off_circuit_2"])
    assert first.attributes["pnu"] == 11179
    assert second.attributes["pnu"] == 12179
    assert first.name == "Heizkreis 1 Sommerabschaltung"
    assert second.name == "Heizkreis 2 Sommerabschaltung"
    assert second.attributes["ecl_name"] == "Optimierung > Sommer- Aus"

    thermostats = [key for key in ids if key.startswith("thermostat")]
    assert sorted(thermostats) == ["thermostat_circuit_1", "thermostat_circuit_2"]
    assert state(ids["thermostat_circuit_2"]).attributes["pnu"] == {
        "mode": 4202,
        "comfort_setpoint": 12180,
        "state": 4212,
    }

    # The hot water functions sit on circuit 3 - with A237's keys.
    assert state(ids["disinfection_temperature"]).attributes["pnu"] == 13125
    assert state(ids["water_heater"]).attributes["pnu"]["setpoint"] == 13190
    assert state(ids["hot_water_mode"]).attributes["pnu"] == 4203


async def test_writing_circuit_2_writes_circuit_2(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """A value set on the second heating circuit lands in 12xxx."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": ids["summer_cut_off_circuit_2"], "value": 17},
        blocking=True,
    )
    unit = connections[-1].for_unit(1)
    assert await unit.read_holding_registers(12178, 1) == [17]


async def test_doubled_sensors_and_pumps_carry_their_circuit(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """S3 and S4 are both a flow; P1 and P5 both a heating pump."""
    hass.config.language = "de"
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    state = hass.states.get

    flow_1 = state(ids["flow_temperature_circuit_1"])
    flow_2 = state(ids["flow_temperature_circuit_2"])
    assert flow_1.attributes["terminal"] == "S3"
    assert flow_2.attributes["terminal"] == "S4"
    assert flow_2.name.endswith("Vorlauftemperatur Kreis 2")
    assert state(ids["return_temperature_circuit_2"]).attributes["terminal"] == "S2"
    # Only one tank: no circuit in its name.
    assert state(ids["storage_temperature"]).attributes["terminal"] == "S6"

    pump_2 = state(ids["heating_pump_circuit_2"])
    assert pump_2.attributes["terminal"] == "relay 5"
    assert pump_2.name.endswith("Heizkreispumpe Kreis 2")
    assert "heating_pump_circuit_2_override" in ids
    assert state(ids["circulation_pump"]).attributes["terminal"] == "relay 3"

    # Each heating circuit reports its own heat, from its own pump.
    available = state(ids["heat_available_circuit_2"]).attributes
    assert available["pnu"] == {"mode": 4202, "state": 4212, "relay_5": 4010}


async def test_references_follow_the_circuits_sensors(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """Circuit 2's desired flow is S4's reference, 12254 - not 12253."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    state = hass.states.get
    assert state(ids["desired_flow_temperature_circuit_1"]).attributes["pnu"] == 11253
    assert state(ids["desired_flow_temperature_circuit_2"]).attributes["pnu"] == 12254
    assert state(ids["return_limit_in_force_circuit_2"]).attributes["pnu"] == 12252
    assert state(ids["desired_tank_temperature"]).attributes["pnu"] == 13256


async def test_each_circuit_has_its_weekly_program(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """Programs at 3110, 3210 and 3310: one per circuit."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    state = hass.states.get
    for key, pnu in (
        ("heating_schedule_monday_p1_start_circuit_1", 3110),
        ("heating_schedule_monday_p1_start_circuit_2", 3210),
        ("hot_water_schedule_monday_p1_start", 3310),
    ):
        assert state(ids[key]).attributes["pnu"] == pnu, key
