"""Base entity for the ECL Comfort 310.

The heating circuit and the hot water tank are their own sub-devices of the
controller; the measurements and the switching outputs belong to the controller
itself.

Setup creates all three devices, and an entity only points at the one it
belongs to. A sub-device has to name its parent by the parent's registry id,
which is only known once the parent exists, so the entities cannot describe
that relationship themselves.
"""

from typing import cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    COMPONENT_HEATING,
    COMPONENT_HEATING_SCHEDULE,
    COMPONENT_HOT_WATER,
    COMPONENT_HOT_WATER_SCHEDULE,
    DOMAIN,
)
from .coordinator import Ecl310Coordinator
from .ecl310_modbus import DeviceInformation, Ecl310Component

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
        self, coordinator: Ecl310Coordinator, key: str, component: str
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._component = component
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"

        self._attr_device_info = DeviceInfo(
            identifiers=device_identifiers(entry, component)
        )

    @property
    def available(self) -> bool:
        """Return whether the sub-system behind this entity answered."""
        return super().available and self.coordinator.answered(self._component)

    @property
    def _subsystem(self) -> Ecl310Component:
        """The library sub-system object this entity reads from."""
        subsystem = getattr(self.coordinator.device, self._component)
        return cast(Ecl310Component, subsystem)
