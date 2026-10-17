"""What the controller reports about itself (issue 32).

Danfoss' communication description VI.LG.V5.02, section 6.12: software,
hardware, code and serial number, production week, and the application.
"""

from __future__ import annotations

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from modbus_connection.mock import MockModbusConnection
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ecl310.diagnostics import async_get_config_entry_diagnostics
from custom_components.ecl310.ecl310_modbus.system_info import (
    SystemInformation,
    decode_hardware,
    decode_production,
    decode_version,
)

from .conftest import APPLICATION_REGISTERS, DOMAIN, ENTRY_DATA
from .test_integration import setup_entry

A237 = "a237_1_v04"
A337 = "a337_2_v02"


def test_the_manuals_examples_decode() -> None:
    """Each worked example of section 6.12 comes out as the manual says."""
    assert decode_hardware(16642) == "A.2"
    assert decode_version(257) == "1.01"
    assert decode_production(2563) == (2010, 3)
    system = SystemInformation.from_registers(
        {19: 3040, 36: 1, 37: 0x0215, 2060: 65, 2061: 214, 2062: 1, 2063: 0x0102}
    )
    assert system.code_number == "087H3040"
    assert system.serial_number == "66069"
    assert system.application_title == "A214.1 V01"
    assert system.profile_key == "a214_1_v01"


def test_nothing_reported_decodes_to_nothing() -> None:
    """A controller that answers zeros - or nothing - is not described."""
    system = SystemInformation.from_registers(dict.fromkeys(range(2060, 2064), 0))
    assert system.application_title is None
    assert SystemInformation.from_registers({}) == SystemInformation()


async def test_the_device_shows_what_the_controller_reports(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """Software, hardware, serial number and application on the device page."""
    entry = await setup_entry(hass, connections)
    assert entry.data["application"] == A237
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), entry.entry_id
    )
    assert device.model_id == "A237.1 V04"
    assert device.sw_version == "1.56"
    assert device.hw_version == "H.3"
    assert device.serial_number == "66069"


async def test_diagnostics_carry_the_identity_without_the_serial(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """Shared diagnostics must not identify the installation."""
    entry = await setup_entry(hass, connections)
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    system = diagnostics["system"]
    assert system["application"] == "A237.1"
    assert system["software"] == "1.56"
    assert system["production"] == (2017, 12)
    assert system["serial_number"] == "**REDACTED**"


async def test_a_wrong_application_raises_a_repair_issue(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """A337.2 chosen, A237.1 running: say so until the options are fixed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**ENTRY_DATA, "application": A337},
        unique_id="192.168.1.100:502:1",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    issues = ir.async_get(hass)
    issue_id = f"application_mismatch_{entry.entry_id}"
    issue = issues.async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    assert issue.translation_placeholders["reported"] == "A237.1 V04"
    assert issue.translation_placeholders["chosen"] == "A337.2 V02"

    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"application": A237}
    )
    await hass.async_block_till_done()
    assert issues.async_get_issue(DOMAIN, issue_id) is None


async def test_the_flow_names_an_application_it_has_no_profile_for(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """It shows what the controller runs and suggests reading everything."""
    import custom_components.ecl310 as integration

    original = integration.ModbusConnection.side_effect

    def reporting_a266(*args: object, **kwargs: object) -> MockModbusConnection:
        connection = original(*args, **kwargs)
        connection.for_unit(1).holding.update(
            dict(zip(APPLICATION_REGISTERS, (65, 266, 1, 0x0300), strict=True))
        )
        return connection

    from custom_components.ecl310 import config_flow

    config_flow.ModbusConnection.side_effect = reporting_a266
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], dict(ENTRY_DATA)
    )
    assert result["description_placeholders"] == {"detected": "A266.1 V03"}
    assert next(iter(result["data_schema"].schema)).default() == "generic"


@pytest.mark.parametrize("application", [A337])
@pytest.mark.parametrize("refused_registers", [set(APPLICATION_REGISTERS)])
async def test_a_controller_not_reporting_it_is_still_probed(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """Without PNU 2060-2063 the refused parameters still single it out."""
    entry = await setup_entry(hass, connections)
    assert entry.data["application"] == A337
    assert (
        ir.async_get(hass).async_get_issue(
            DOMAIN, f"application_mismatch_{entry.entry_id}"
        )
        is None
    )
