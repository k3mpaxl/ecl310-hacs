"""Each entity names the Danfoss parameter numbers and terminals behind it (issue 35).

The ECL manuals refer to everything by PNU, so the entities carry it as the
``pnu`` attribute, and sensor inputs and outputs carry their ``terminal``. The
numbers below are the ones in Danfoss' communication description VI.LG.V5.02.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from modbus_connection.mock import MockModbusConnection

from custom_components.ecl310.diagnostics import async_get_config_entry_diagnostics

from .conftest import HOLDING
from .test_a266 import A266, A266_SENSORS
from .test_integration import entity_ids, setup_entry


async def test_single_datapoints_show_their_pnu_and_terminal(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """A sensor, a setting and a pump each name one PNU."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)

    def attributes(key: str) -> dict:
        return dict(hass.states.get(ids[key]).attributes)

    flow = attributes("flow_temperature")
    assert flow["pnu"] == 10203
    assert flow["terminal"] == "S3"

    curve = attributes("heat_curve")
    assert curve["pnu"] == 11175
    assert "terminal" not in curve

    pump = attributes("heating_pump")
    assert pump["pnu"] == 4006
    assert pump["terminal"] == "relay 1"
    override = attributes("heating_pump_override")
    assert override["pnu"] == 4066
    assert override["terminal"] == "relay 1"

    assert attributes("hot_water_mode")["pnu"] == 4202


async def test_combined_entities_list_their_pnus_by_value(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """The thermostat and the water heater name each value apart."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    state = hass.states.get

    thermostat = state(ids["thermostat"]).attributes
    assert thermostat["pnu"] == {"mode": 4201, "comfort_setpoint": 11180, "state": 4211}
    assert "terminal" not in thermostat

    water_heater = state(ids["water_heater"]).attributes
    assert water_heater["pnu"] == {
        "mode": 4202,
        "setpoint": 12190,
        "storage_temperature": 10206,
    }
    assert water_heater["terminal"] == "S6"

    heat_available = state(ids["heat_available"]).attributes
    assert heat_available["pnu"] == {"mode": 4201, "state": 4211, "relay_1": 4006}
    assert heat_available["terminal"] == "relay 1"


async def test_own_attributes_stay_and_the_boost_names_none(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """The integration's own boost has no PNU; other attributes are kept."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    state = hass.states.get

    disinfection = state(ids["disinfection"]).attributes
    assert disinfection["pnu"] == 12125
    assert "temperature_when_on" in disinfection

    for key in ("hot_water_boost", "hot_water_boost_on_raise"):
        assert "pnu" not in state(ids[key]).attributes


async def test_diagnostics_list_each_entity_with_its_pnus(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """The download maps entities to PNUs, for comparing with the manual."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    entities = diagnostics["entities"]
    assert entities[ids["flow_temperature"]] == {"pnu": 10203, "terminal": "S3"}
    assert entities[ids["heat_curve"]] == {"pnu": 11175}
    assert ids["hot_water_boost"] not in entities


@pytest.mark.parametrize("application", [A266])
@pytest.mark.parametrize("register_image", [{**HOLDING, **A266_SENSORS}])
async def test_a266_names_its_own_terminals(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """S4 is the hot water flow; the water heater has no tank sensor to name."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    state = hass.states.get

    hot_water_flow = state(ids["hot_water_flow_temperature"]).attributes
    assert hot_water_flow["pnu"] == 10204
    assert hot_water_flow["terminal"] == "S4"
    assert state(ids["heating_pump"]).attributes["terminal"] == "relay 2"

    water_heater = state(ids["water_heater"]).attributes
    assert "storage_temperature" not in water_heater["pnu"]
    assert "terminal" not in water_heater


async def test_the_menu_name_is_the_controllers_own(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """``ecl_name`` is where the display shows it, in the user's language."""
    hass.config.language = "de"
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    state = hass.states.get

    assert state(ids["summer_cut_off"]).attributes["ecl_name"] == (
        "Optimierung > Sommer- Aus"
    )
    assert state(ids["disinfection_temperature"]).attributes["ecl_name"] == (
        "LEGIO Desinfektion > Gewünschte T"
    )
    thermostat = state(ids["thermostat"]).attributes["ecl_name"]
    assert thermostat["comfort_setpoint"] == "Allg. Parameter > T-Komfort Soll"
    # A sensor input is no parameter: it has a PNU, but no menu entry.
    assert "ecl_name" not in state(ids["flow_temperature"]).attributes
