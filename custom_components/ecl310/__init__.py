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
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from modbus_connection import ModbusError, ModbusTcpParams
from modbus_connection.tmodbus import ModbusConnection

from .boost import STORAGE_VERSION, HotWaterBoost
from .const import (
    APPLICATION_GENERIC,
    CONF_APPLICATION,
    CONF_FRAMER,
    CONF_UNIT_ID,
    DEFAULT_FRAMER,
    DOMAIN,
    LOGGER,
)
from .coordinator import Ecl310ConfigEntry, Ecl310Coordinator
from .data import Ecl310Data
from .ecl310_modbus import PROFILES, ApplicationProfile, Ecl310
from .entity import SUB_DEVICES, controller_device_info, device_identifiers

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from modbus_connection import ModbusUnit

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


def application_key(entry: Ecl310ConfigEntry) -> str | None:
    """Return the application an entry was set to, if it was set to one yet."""
    return entry.options.get(CONF_APPLICATION, entry.data.get(CONF_APPLICATION))


async def _async_application(
    hass: HomeAssistant, entry: Ecl310ConfigEntry, unit: ModbusUnit
) -> ApplicationProfile | None:
    """Return the profile of the controller's application, if there is one.

    An entry set up before applications could be chosen has none stored: the
    application is detected once and stored, so the next start reads only the
    parameters it has. The options let the user change it.
    """
    key = application_key(entry)
    if key is None:
        detection = await Ecl310.async_detect_application(unit)
        detected = detection.application
        key = detected.key if detected else APPLICATION_GENERIC
        LOGGER.info(
            "Detected application %s (reported %s, answered %s, refused %s)",
            detected.title if detected else "unknown",
            detection.reported,
            sorted(detection.answered),
            sorted(detection.refused),
        )
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_APPLICATION: key}
        )
    if key != APPLICATION_GENERIC and key not in PROFILES:
        LOGGER.warning("Unknown application %s; reading every parameter", key)
    return PROFILES.get(key)


def _check_application(
    hass: HomeAssistant,
    entry: Ecl310ConfigEntry,
    application: ApplicationProfile | None,
    reported: str | None,
) -> None:
    """Raise a repair issue while the chosen application is not the running one.

    Only a chosen profile can be wrong: "Other application" reads everything.
    The issue goes away once the options name the application the controller
    reports.
    """
    issue_id = f"application_mismatch_{entry.entry_id}"
    if application is None or reported is None or reported == application.title:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return
    LOGGER.warning(
        "The controller reports application %s, but %s is chosen",
        reported,
        application.title,
    )
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="application_mismatch",
        translation_placeholders={
            "chosen": application.title,
            "reported": reported,
            "title": entry.title,
        },
    )


async def async_setup_entry(hass: HomeAssistant, entry: Ecl310ConfigEntry) -> bool:
    """Set up the ECL Comfort 310 from a config entry."""
    connection = ModbusConnection(connection_params(dict(entry.data)))
    unit = connection.for_unit(int(entry.data[CONF_UNIT_ID]))
    try:
        application = await _async_application(hass, entry, unit)
    except ModbusError as err:
        await connection.close()
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
            translation_placeholders={"error": str(err)},
        ) from err
    device = Ecl310(unit, application=application)
    try:
        system = await device.async_read_system_information()
    except ModbusError as err:
        await connection.close()
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
            translation_placeholders={"error": str(err)},
        ) from err
    _check_application(hass, entry, application, system.application_title)
    coordinator = Ecl310Coordinator(hass, entry, device)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await connection.close()
        raise

    boost = HotWaterBoost(
        hass,
        coordinator,
        Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.boost"),
    )
    await boost.async_load()
    entry.async_on_unload(
        coordinator.async_add_listener(boost.async_coordinator_updated)
    )
    entry.runtime_data = Ecl310Data(
        coordinator=coordinator, connection=connection, boost=boost
    )
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
