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
    assert hass.states.get(eid).attributes["max"] == maximum
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
        await hass.services.async_call(
            "number", "set_value", {"entity_id": eid, "value": 100}, blocking=True
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
