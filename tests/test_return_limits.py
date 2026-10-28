"""Installer return-limit settings in every supported application."""

from __future__ import annotations

import pytest
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from modbus_connection.mock import MockModbusConnection
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ecl310.ecl310_modbus import PROFILES, Ecl310
from custom_components.ecl310.ecl310_modbus.exceptions import Ecl310ValueValidationError

from .conftest import DOMAIN, ENTRY_DATA, HOLDING
from .test_integration import entity_ids, setup_entry

HEATING_FIELDS = {
    "return_limit_x1": 31,
    "return_limit_y1": 32,
    "return_limit_x2": 33,
    "return_limit_y2": 34,
    "return_limit_influence_max": 35,
    "return_limit_influence_min": 36,
    "return_limit_adaptation_time": 37,
}
HOT_WATER_FIELDS = {key: value for key, value in HEATING_FIELDS.items() if value >= 35}


@pytest.mark.parametrize("application", sorted(PROFILES))
async def test_settings_follow_profile_and_circuit(
    hass: HomeAssistant, connections: list[MockModbusConnection], application: str
) -> None:
    """Only supported PNUs appear, on their circuit and disabled by default."""
    entry = await setup_entry(hass, connections)
    device = entry.runtime_data.coordinator.device
    assert device.application.key == application
    ids = entity_ids(hass, entry)
    registry = er.async_get(hass)
    devices = dr.async_get(hass)
    for circuit in device.circuits:
        fields = HEATING_FIELDS if circuit.kind == "heating" else HOT_WATER_FIELDS
        for field, suffix in fields.items():
            pnu = 10000 + circuit.number * 1000 + suffix
            key = ("hot_water_" if circuit.kind == "hot_water" else "") + field
            if circuit.numbered:
                key += f"_circuit_{circuit.number}"
            if pnu not in device.application.parameters:
                assert key not in ids
                continue
            entity = registry.async_get(ids[key])
            assert entity.disabled_by == er.RegistryEntryDisabler.INTEGRATION
            assert entity.entity_category == EntityCategory.CONFIG
            circuit_device = devices.async_get_device_by_identifier(
                (DOMAIN, f"{entry.entry_id}_{circuit.component}"), entry.entry_id
            )
            assert circuit_device is not None
            assert entity.device_id == circuit_device.id
            component = getattr(device, circuit.component)
            metadata = component.metadata_for(field)
            parameter = device.application.parameters[pnu]
            assert metadata.parameter_id == pnu
            assert metadata.number.min_value == pytest.approx(
                parameter.minimum / parameter.scale
            )
            assert metadata.number.max_value == pytest.approx(
                parameter.maximum / parameter.scale
            )
            assert metadata.number.step == pytest.approx(1 / parameter.scale)
            assert device.supports(circuit.component, field)


@pytest.mark.parametrize("application", ["a266_10_v03"])
@pytest.mark.parametrize(
    "register_image",
    [{**HOLDING, 11030: (-15 & 0xFFFF), 11034: (-40 & 0xFFFF), 12034: 25}],
)
async def test_read_and_write_on_both_circuits(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """A266 reads and writes signed/scaled values to the correct registers."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    registry = er.async_get(hass)
    keys = (
        "return_limit_x1",
        "return_limit_influence_max",
        "hot_water_return_limit_influence_max",
    )
    for key in keys:
        registry.async_update_entity(ids[key], disabled_by=None)
    await hass.async_block_till_done()
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    for key, expected, pnu in zip(
        keys, ("-15", "-4.0", "2.5"), (11031, 11035, 12035), strict=True
    ):
        state = hass.states.get(ids[key])
        assert float(state.state) == float(expected)
        assert state.attributes["pnu"] == pnu
        assert state.attributes["ecl_name"]
    influence = hass.states.get(ids["return_limit_influence_max"])
    assert (
        influence.attributes["min"],
        influence.attributes["max"],
        influence.attributes["step"],
    ) == (-9.9, 9.9, 0.1)
    unit = connections[-1].for_unit(ENTRY_DATA["unit_id"])
    for key, value, address, raw in (
        (keys[0], -20, 11030, -20 & 0xFFFF),
        (keys[1], -3.5, 11034, -35 & 0xFFFF),
        (keys[2], 1.5, 12034, 15),
    ):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": ids[key], "value": value},
            blocking=True,
        )
        assert unit.holding[address] == raw

    # The model rejects out-of-domain values before any register is changed.
    with pytest.raises(Ecl310ValueValidationError):
        await entry.runtime_data.coordinator.device.heating.write(
            "return_limit_x1", -61
        )
    with pytest.raises(Ecl310ValueValidationError):
        await entry.runtime_data.coordinator.device.hot_water.write(
            "return_limit_influence_max", 10
        )
    assert unit.holding[11030] == (-20 & 0xFFFF)
    assert unit.holding[12034] == 15


async def test_unknown_application_does_not_poll_new_settings(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """The generic fallback keeps its existing behaviour and exposes none of these."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**ENTRY_DATA, "application": "generic"},
        unique_id="192.168.1.100:502:1",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    ids = entity_ids(hass, entry)
    assert not any(key in ids for key in HEATING_FIELDS)
    device: Ecl310 = entry.runtime_data.coordinator.device
    assert not device.supports("heating", "return_limit_x1")
    assert "return_limit_x1" not in device.heating.resolved_fields
    unit = connections[-1].for_unit(ENTRY_DATA["unit_id"])
    assert not any(
        event.address <= 11030 < event.address + event.count
        for event in unit.read_events
    )


@pytest.mark.parametrize("application", ["a266_10_v03"])
@pytest.mark.parametrize("refused_registers", [{11030}])
async def test_refused_setting_does_not_disable_heating(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """A controller refusing one optional setting still supplies other entities."""
    entry = await setup_entry(hass, connections)
    coordinator = entry.runtime_data.coordinator
    ids = entity_ids(hass, entry)
    assert "return_limit_x1" in coordinator.refused("heating")
    assert "heating" not in coordinator.data.failed
    assert hass.states.get(ids["thermostat"]).state not in ("unavailable", "unknown")
