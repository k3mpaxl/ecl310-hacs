"""Diagnostics support for the ECL Comfort 310.

The most useful payload for a Modbus device is the raw register map: every
register the integration reads, with the value the controller returned. It
replays straight back into the library's mock backend, so a downloaded snapshot
can back a regression test without hardware.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from modbus_connection import ModbusError

from .coordinator import Ecl310ConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: Ecl310ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator
    diagnostics: dict[str, Any] = {
        "updated": coordinator.data.updated,
        "failed": {name: str(error) for name, error in coordinator.data.failed.items()},
    }
    try:
        diagnostics["registers"] = await coordinator.device.async_read_raw()
    except ModbusError as err:
        diagnostics["registers_error"] = str(err)
    return diagnostics
