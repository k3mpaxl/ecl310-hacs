"""Binary sensor platform - the controller's switching outputs.

Which pump or actuator sits on which triac or relay is decided by the installed
application key and the wiring. An output the application key names is enabled
and carries that name; the rest are named after their terminal and disabled by
default - enable the ones your installation actually uses.

These report what an output is doing. Forcing one is the select platform's job:
the state register is a result and the controller refuses a write to it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import COMPONENT_OUTPUTS
from .coordinator import Ecl310ConfigEntry, Ecl310Coordinator
from .ecl310_modbus import Ecl310
from .ecl310_modbus.configurations import RELAY_ASSIGNMENTS, RELAY_ASSIGNMENTS_BY_NUMBER
from .ecl310_modbus.subsystems.outputs import RELAY_COUNT, TRIAC_COUNT
from .entity import Ecl310Entity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class Ecl310BinarySensorDescription(BinarySensorEntityDescription):
    """Describes a binary sensor reading one output register."""

    component: str
    value_fn: Callable[[Ecl310], int | None]


def _output(kind: str, number: int) -> Ecl310BinarySensorDescription:
    """Describe one unnamed triac or relay output, by terminal number."""
    attribute = f"{kind}_{number}"
    return Ecl310BinarySensorDescription(
        key=attribute,
        translation_key=kind,
        translation_placeholders={"number": str(number)},
        component=COMPONENT_OUTPUTS,
        value_fn=lambda device, name=attribute: getattr(device.outputs, name),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    )


def _pump(key: str, number: int) -> Ecl310BinarySensorDescription:
    """Describe a relay the application key names, by what it drives."""
    return Ecl310BinarySensorDescription(
        key=key,
        translation_key=key,
        component=COMPONENT_OUTPUTS,
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda device, name=f"relay_{number}": getattr(device.outputs, name),
    )


BINARY_SENSORS: tuple[Ecl310BinarySensorDescription, ...] = (
    *(_pump(assignment.key, assignment.number) for assignment in RELAY_ASSIGNMENTS),
    *(_output("triac", number) for number in range(1, TRIAC_COUNT + 1)),
    *(
        _output("relay", number)
        for number in range(1, RELAY_COUNT + 1)
        if number not in RELAY_ASSIGNMENTS_BY_NUMBER
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: Ecl310ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ECL output binary sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        Ecl310BinarySensor(coordinator, description) for description in BINARY_SENSORS
    )


class Ecl310BinarySensor(Ecl310Entity, BinarySensorEntity):
    """One switching output."""

    entity_description: Ecl310BinarySensorDescription

    def __init__(
        self,
        coordinator: Ecl310Coordinator,
        description: Ecl310BinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, description.key, description.component)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return whether the output is switched on."""
        value = self.entity_description.value_fn(self.coordinator.device)
        if value is None:
            return None
        return value != 0
