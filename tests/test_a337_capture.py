"""The A337.2 controller from issue 13, as its owner reported it after 0.9.0.

The register image comes from @ljossa's diagnostics download; the simulated
controller refuses the parameters A337.2 V02 lacks, as the real one does. Each
check below is something the owner confirmed on the real installation.
"""

from __future__ import annotations

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from modbus_connection.mock import MockModbusConnection

from custom_components.ecl310.ecl310_modbus import PROFILES, Ecl310

from .conftest import DOMAIN, ENTRY_DATA
from .register_images import HOLDING_A337_2_V02
from .test_integration import entity_ids, setup_entry

A337 = "a337_2_v02"

pytestmark = [
    pytest.mark.parametrize("application", [A337]),
    pytest.mark.parametrize("register_image", [HOLDING_A337_2_V02]),
]


async def test_the_application_is_detected(
    connections: list[MockModbusConnection],
) -> None:
    """The owner: "the application was detected automatically as A337.2 V02"."""
    from custom_components.ecl310 import ModbusConnection

    detection = await Ecl310.async_detect_application(
        ModbusConnection(None).for_unit(ENTRY_DATA["unit_id"])
    )
    assert detection.application is PROFILES[A337]


async def test_the_flow_suggests_a337(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """The setup flow offers the detected application first."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], dict(ENTRY_DATA)
    )
    assert result["step_id"] == "application"
    assert result["description_placeholders"] == {"detected": "A337.2 V02"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"application": A337}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_every_subsystem_reads_and_shows_what_the_owner_saw(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """Outputs work, pumps and "heat available" have values, nothing failed."""
    entry = await setup_entry(hass, connections)
    coordinator = entry.runtime_data.coordinator
    assert coordinator.data.failed == {}
    assert len(coordinator.data.updated) == 6
    assert not any(coordinator.refused(name) for name in coordinator.data.updated)

    ids = entity_ids(hass, entry)
    state = hass.states.get
    assert state(ids["heating_pump"]).state == "on"
    assert state(ids["circulation_pump"]).state == "on"
    assert state(ids["storage_charge_pump"]).state == "off"
    for pump in ("heating_pump", "circulation_pump", "storage_charge_pump"):
        assert state(ids[f"{pump}_override"]).state == "auto"
    assert state(ids["heat_available"]).state == "on"


async def test_disinfection_is_off_with_friday_stored(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """9 reads as off; the stored weekday is Friday (bit 4), as Danfoss defines."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    state = hass.states.get
    assert state(ids["disinfection"]).state == "off"
    assert state(ids["disinfection_temperature"]).state == STATE_UNKNOWN
    assert state(ids["disinfection_friday"]).state == "on"
    for day in ("monday", "tuesday", "wednesday", "thursday", "saturday", "sunday"):
        assert state(ids[f"disinfection_{day}"]).state == "off"
