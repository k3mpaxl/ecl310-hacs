"""Base entity for the ECL Comfort 310.

The heating circuit and the hot water tank are their own sub-devices of the
controller; the measurements and the switching outputs belong to the controller
itself.

Setup creates all three devices, and an entity only points at the one it
belongs to. A sub-device has to name its parent by the parent's registry id,
which is only known once the parent exists, so the entities cannot describe
that relationship themselves.
"""

from collections.abc import Awaitable
from typing import cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from modbus_connection import ModbusError

from .const import (
    COMPONENT_HEATING,
    COMPONENT_HEATING_SCHEDULE,
    COMPONENT_HOT_WATER,
    COMPONENT_HOT_WATER_SCHEDULE,
    DOMAIN,
)
from .coordinator import Ecl310Coordinator
from .ecl310_modbus import DatapointMetadata, DeviceInformation, Ecl310Component

# Sub-devices, keyed by the library sub-system they read from: the suffix that
# makes their identifier, and the key their name is translated under.
SUB_DEVICES: dict[str, tuple[str, str]] = {
    COMPONENT_HEATING: ("heating", "heating_circuit"),
    COMPONENT_HOT_WATER: ("hot_water", "hot_water"),
}


#: Sub-systems that belong to another sub-system's device. A circuit's weekly
#: program is part of that circuit, not a device of its own.
SHARED_DEVICES: dict[str, str] = {
    COMPONENT_HEATING_SCHEDULE: COMPONENT_HEATING,
    COMPONENT_HOT_WATER_SCHEDULE: COMPONENT_HOT_WATER,
}


def device_identifiers(entry: ConfigEntry, component: str) -> set[tuple[str, str]]:
    """Identify the device an entity of this sub-system belongs to."""
    component = SHARED_DEVICES.get(component, component)
    if (sub := SUB_DEVICES.get(component)) is None:
        return {(DOMAIN, entry.entry_id)}
    return {(DOMAIN, f"{entry.entry_id}_{sub[0]}")}


def controller_device_info(entry: ConfigEntry, info: DeviceInformation) -> DeviceInfo:
    """Describe the controller itself, for setup to register."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer=info.manufacturer,
        model=info.model,
        name=info.model,
        sw_version=info.firmware_version,
        serial_number=info.serial_number,
    )


class Ecl310Entity(CoordinatorEntity[Ecl310Coordinator]):
    """Common identity, device info and availability for every ECL entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: Ecl310Coordinator,
        key: str,
        component: str,
        fields: tuple[str, ...] = (),
    ) -> None:
        """Initialize the entity.

        ``fields`` names the sub-system fields the entity reads. It stays
        unavailable if the controller does not serve any of them.
        """
        super().__init__(coordinator)
        self._component = component
        self._fields = frozenset(fields)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"

        self._attr_device_info = DeviceInfo(
            identifiers=device_identifiers(entry, component)
        )

    @property
    def available(self) -> bool:
        """Return whether the sub-system and the fields behind this entity answered."""
        return (
            super().available
            and self.coordinator.answered(self._component)
            and self._fields.isdisjoint(self.coordinator.refused(self._component))
        )

    @property
    def _subsystem(self) -> Ecl310Component:
        """The library sub-system object this entity reads from."""
        subsystem = getattr(self.coordinator.device, self._component)
        return cast(Ecl310Component, subsystem)

    def _metadata(self, attribute: str) -> DatapointMetadata:
        """Return the library's metadata for one of this sub-system's datapoints."""
        return self._subsystem.require_metadata_for(attribute)

    async def _async_write(self, write: Awaitable[None]) -> None:
        """Await a write, turning what it raises into a Home Assistant error.

        A value outside the controller's domain is the caller's mistake and
        becomes a ``ServiceValidationError``; a controller that refuses or does
        not answer becomes a ``HomeAssistantError``. Both carry a translated
        message instead of a traceback.
        """
        try:
            await write
        except ValueError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_value",
                translation_placeholders={"error": str(err)},
            ) from err
        except ModbusError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"error": str(err)},
            ) from err
