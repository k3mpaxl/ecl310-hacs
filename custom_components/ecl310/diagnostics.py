"""Diagnostics support for the ECL Comfort 310.

The most useful payload for a Modbus device is the raw register map: every
register the integration reads, with the value the controller returned. It
replays straight back into the library's mock backend, so a downloaded snapshot
can back a regression test without hardware.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant
from modbus_connection import ModbusError

from .coordinator import Ecl310ConfigEntry

#: The controller's serial number identifies one installation.
TO_REDACT = {"serial_number"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: Ecl310ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator
    application = coordinator.device.application
    diagnostics: dict[str, Any] = {
        "application": application.title if application else None,
        "system": (
            async_redact_data(asdict(system), TO_REDACT)
            if (system := coordinator.device.system) is not None
            else None
        ),
        "updated": coordinator.data.updated,
        "failed": {name: str(error) for name, error in coordinator.data.failed.items()},
        "refused": {
            name: sorted(coordinator.refused(name)) for name in coordinator.data.updated
        },
    }
    try:
        diagnostics["registers"] = await coordinator.device.async_read_raw()
    except ModbusError as err:
        diagnostics["registers_error"] = str(err)
    return diagnostics
