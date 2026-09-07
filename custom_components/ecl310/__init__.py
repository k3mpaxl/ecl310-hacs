"""The Danfoss ECL Comfort 310 custom integration.

Unlike the version of this integration written for Home Assistant core, the
custom integration owns its Modbus connection: the shared-connection API the
core version uses (``homeassistant.components.modbus.async_get_unit``) is not
available to custom integrations on every release. One config entry therefore
means one connection, opened here and closed when the entry unloads.

The device library is vendored under ``ecl310_modbus`` so the integration
installs from HACS without a separate PyPI release.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.helpers import device_registry as dr
from modbus_connection import ModbusTcpParams
from modbus_connection.tmodbus import ModbusConnection

from .const import CONF_FRAMER, CONF_UNIT_ID, DEFAULT_FRAMER
from .coordinator import Ecl310ConfigEntry, Ecl310Coordinator
from .data import Ecl310Data
from .ecl310_modbus import Ecl310
from .entity import SUB_DEVICES, controller_device_info, device_identifiers

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
    Platform.WATER_HEATER,
]


def connection_params(data: dict) -> ModbusTcpParams:
    """Build the link parameters an entry's data describes."""
    return ModbusTcpParams(
        host=data[CONF_HOST],
        port=int(data[CONF_PORT]),
        framer=data.get(CONF_FRAMER, DEFAULT_FRAMER),
    )


async def async_setup_entry(hass: HomeAssistant, entry: Ecl310ConfigEntry) -> bool:
    """Set up the ECL Comfort 310 from a config entry."""
    connection = ModbusConnection(connection_params(dict(entry.data)))
    device = Ecl310(connection.for_unit(int(entry.data[CONF_UNIT_ID])))
    coordinator = Ecl310Coordinator(hass, entry, device)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await connection.close()
        raise

    entry.runtime_data = Ecl310Data(coordinator=coordinator, connection=connection)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    # Every device is created here: a sub-device names its parent by the
    # parent's registry id, so the controller has to exist first.
    info = coordinator.device.info
    device_registry = dr.async_get(hass)
    controller = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        **controller_device_info(entry, info),
    )
    for component in SUB_DEVICES:
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers=device_identifiers(entry, component),
            manufacturer=info.manufacturer,
            translation_key=SUB_DEVICES[component][1],
            via_device_id=controller.id,
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: Ecl310ConfigEntry) -> bool:
    """Unload a config entry and close the link it owns."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    await entry.runtime_data.connection.close()
    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: Ecl310ConfigEntry) -> None:
    """Reload the config entry after its options changed."""
    await hass.config_entries.async_reload(entry.entry_id)
