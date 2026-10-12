"""Binary sensor platform - the controller's switching outputs.

Which pump or actuator sits on which triac or relay is decided by the installed
application key and the wiring. An output the application key names is enabled
and carries that name; the rest are named after their terminal and disabled by
default - enable the ones your installation actually uses.

These report what an output is doing. Forcing one is the select platform's job:
the state register is a result and the controller refuses a write to it.

One sensor is derived rather than read: whether the heating circuit is
delivering heat right now. Radiator valves that can be told so - a Danfoss Ally
takes it as "HeatAvailable" - stop asking for heat the system is not supplying.
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

from .const import COMPONENT_HEATING, COMPONENT_OUTPUTS
from .coordinator import Ecl310ConfigEntry, Ecl310Coordinator
from .ecl310_modbus import CircuitState, Ecl310, OperatingMode
from .ecl310_modbus.configurations import (
    RELAY_ASSIGNMENTS,
    RELAY_ASSIGNMENTS_BY_KEY,
    RELAY_ASSIGNMENTS_BY_NUMBER,
)
from .ecl310_modbus.subsystems.outputs import RELAY_COUNT, TRIAC_COUNT
from .entity import Ecl310Entity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class Ecl310BinarySensorDescription(BinarySensorEntityDescription):
    """Describes a binary sensor reading one output register."""

    component: str
    field: str
    value_fn: Callable[[Ecl310], int | None]


def _output(kind: str, number: int) -> Ecl310BinarySensorDescription:
    """Describe one unnamed triac or relay output, by terminal number."""
    attribute = f"{kind}_{number}"
    return Ecl310BinarySensorDescription(
        key=attribute,
        translation_key=kind,
        translation_placeholders={"number": str(number)},
        component=COMPONENT_OUTPUTS,
        field=attribute,
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
        field=f"relay_{number}",
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
        [
            *(
                Ecl310BinarySensor(coordinator, description)
                for description in BINARY_SENSORS
            ),
            Ecl310HeatAvailable(coordinator),
        ]
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
        super().__init__(
            coordinator, description.key, description.component, (description.field,)
        )
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return whether the output is switched on."""
        value = self.entity_description.value_fn(self.coordinator.device)
        if value is None:
            return None
        return value != 0


#: Where in the weekly program the circuit counts as heating. Pre-comfort is
#: the circuit already heating up for the comfort period that follows.
_HEATING_STATES = frozenset({CircuitState.COMFORT, CircuitState.PRE_COMFORT})


def heat_available(
    mode: OperatingMode | None, state: CircuitState | None, pump: int | None
) -> bool | None:
    """Return whether the heating circuit is delivering heat right now.

    The pump has to run, and the circuit has to be in comfort: constant
    comfort, or the weekly program inside (or heating up for) a comfort
    period. Setback, frost protection and a summer cut-off - which stops the
    pump - all count as no heat.
    """
    if mode is None or pump is None:
        return None
    if not pump:
        return False
    if mode == OperatingMode.COMFORT:
        return True
    if mode == OperatingMode.SCHEDULED:
        return None if state is None else state in _HEATING_STATES
    return False


class Ecl310HeatAvailable(Ecl310Entity, BinarySensorEntity):
    """Whether the heating circuit is supplying heat - for radiator valves."""

    _attr_translation_key = "heat_available"
    # No device class: "heat" would read hot/normal; the states are translated.
    _attr_icon = "mdi:fire-circle"

    def __init__(self, coordinator: Ecl310Coordinator) -> None:
        """Initialize the sensor on the heating circuit's device."""
        super().__init__(
            coordinator, "heat_available", COMPONENT_HEATING, ("mode", "state")
        )
        self._pump_field = f"relay_{RELAY_ASSIGNMENTS_BY_KEY['heating_pump'].number}"

    @property
    def available(self) -> bool:
        """Return whether the circuit and the pump output both answered."""
        return (
            super().available
            and self.coordinator.answered(COMPONENT_OUTPUTS)
            and self._pump_field not in self.coordinator.refused(COMPONENT_OUTPUTS)
        )

    @property
    def is_on(self) -> bool | None:
        """Return whether heat is available."""
        device = self.coordinator.device
        return heat_available(
            device.heating.mode,
            device.heating.state,
            getattr(device.outputs, self._pump_field),
        )
