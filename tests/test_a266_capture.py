"""The A266.10 controller from issue 35, as its owner's diagnostics captured it.

The register image comes from @obelixed's diagnostics download (0.12.0); the
simulated controller refuses the parameters A266.10 V03 lacks and reports the
application, as the real one does. The relay and valve assignment checked here
is the one the owner gave for his installation.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from modbus_connection.mock import MockModbusConnection

from custom_components.ecl310.ecl310_modbus import PROFILES, Ecl310

from .conftest import ENTRY_DATA
from .register_images import HOLDING_A266_10_V03
from .test_integration import entity_ids, setup_entry

A266 = "a266_10_v03"

pytestmark = [
    pytest.mark.parametrize("application", [A266]),
    pytest.mark.parametrize("register_image", [HOLDING_A266_10_V03]),
]


async def test_the_application_is_detected(
    connections: list[MockModbusConnection],
) -> None:
    """The controller reports A266.10 V03, and that profile is chosen."""
    from custom_components.ecl310 import ModbusConnection

    detection = await Ecl310.async_detect_application(
        ModbusConnection(None).for_unit(ENTRY_DATA["unit_id"])
    )
    assert detection.application is PROFILES[A266]


async def test_everything_reads_and_nothing_is_refused(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """As in the owner's download: every sub-system answered, none refused."""
    entry = await setup_entry(hass, connections)
    coordinator = entry.runtime_data.coordinator
    assert coordinator.data.failed == {}
    assert not any(coordinator.refused(name) for name in coordinator.data.updated)


async def test_the_sensors_show_the_owners_temperatures(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """S1-S6 under A266.10's roles, with the captured readings."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    readings = {
        "outdoor_temperature": "10.52",
        "secondary_return_temperature": "25.36",
        "flow_temperature": "27.48",
        "hot_water_flow_temperature": "44.47",
        "return_temperature": "25.59",
        "hot_water_return_temperature": "27.6",
        "desired_flow_temperature": "28.45",
        "desired_hot_water_flow_temperature": "40.0",
    }
    for key, value in readings.items():
        assert hass.states.get(ids[key]).state == value, key


async def test_pumps_and_valves_as_the_owner_wired_them(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """Heating pump on relay 2 running; circulation pump on relay 1 idle."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    state = hass.states.get

    assert state(ids["heating_pump"]).state == "on"
    assert state(ids["heating_pump"]).attributes["terminal"] == "relay 2"
    assert state(ids["circulation_pump"]).state == "off"
    assert state(ids["circulation_pump"]).attributes["terminal"] == "relay 1"
    for pump in ("heating_pump", "circulation_pump"):
        assert state(ids[f"{pump}_override"]).state == "auto"
    # Comfort, scheduled, pump running: heat is available.
    assert state(ids["heat_available"]).state == "on"

    registry = er.async_get(hass)
    for valve in ("hot_water_valve_open", "hot_water_valve_close"):
        assert registry.async_get(ids[valve]).disabled_by is not None


async def test_the_disinfection_runs_on_sundays_at_70(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """On at 70 °C, Sunday only (bit 6), from 22:30 for 90 minutes."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    state = hass.states.get
    assert state(ids["disinfection"]).state == "on"
    assert state(ids["disinfection_temperature"]).state == "70"
    assert state(ids["disinfection_sunday"]).state == "on"
    assert state(ids["disinfection_monday"]).state == "off"
    assert state(ids["disinfection_start"]).state == "22:30:00"
    assert state(ids["disinfection_duration"]).state == "90"
