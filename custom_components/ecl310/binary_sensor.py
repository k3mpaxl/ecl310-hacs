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

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import COMPONENT_HEATING, COMPONENT_OUTPUTS
from .coordinator import Ecl310ConfigEntry, Ecl310Coordinator
from .ecl310_modbus import Circuit, CircuitState, Ecl310, OperatingMode
from .ecl310_modbus.subsystems.outputs import RELAY_COUNT, TRIAC_COUNT
from .entity import Ecl310Entity, circuit_key, role_circuit, role_name, supported

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class Ecl310BinarySensorDescription(BinarySensorEntityDescription):
    """Describes a binary sensor reading one output register."""

    component: str
    field: str


def _output(
    kind: str, number: int, *, shown: bool = False
) -> Ecl310BinarySensorDescription:
    """Describe one unnamed triac or relay output, by terminal number.

    Hidden by default; ``shown`` while the application's relays are not known,
    so the pumps can at least be told apart by number.
    """
    attribute = f"{kind}_{number}"
    return Ecl310BinarySensorDescription(
        key=attribute,
        translation_key=kind,
        translation_placeholders={"number": str(number)},
        component=COMPONENT_OUTPUTS,
        field=attribute,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=shown,
    )


def _pump(key: str, number: int) -> Ecl310BinarySensorDescription:
    """Describe a relay the application key names, by what it drives."""
    translation_key, placeholders = role_name(key)
    return Ecl310BinarySensorDescription(
        key=key,
        translation_key=translation_key,
        translation_placeholders=placeholders,
        component=COMPONENT_OUTPUTS,
        field=f"relay_{number}",
        device_class=BinarySensorDeviceClass.RUNNING,
    )


def _valve(key: str, number: int) -> Ecl310BinarySensorDescription:
    """Describe a triac the application wires a motorised valve to.

    Disabled by default: a three-point valve is pulsed open and shut all day,
    which says little and fills the recorder.
    """
    translation_key, placeholders = role_name(key)
    return Ecl310BinarySensorDescription(
        key=key,
        translation_key=translation_key,
        translation_placeholders=placeholders,
        component=COMPONENT_OUTPUTS,
        field=f"triac_{number}",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    )


def binary_sensors(device: Ecl310) -> tuple[Ecl310BinarySensorDescription, ...]:
    """Describe the output sensors for this controller's application.

    The pumps and valves it names by what they drive; every other output by
    number - the relays shown while the application's assignment is unknown.
    """
    relays = device.relay_assignments
    triacs = device.triac_assignments
    named_relays = {assignment.number for assignment in relays or ()}
    named_triacs = {assignment.number for assignment in triacs or ()}
    return (
        *(_pump(a.key, a.number) for a in relays or ()),
        *(_valve(a.key, a.number) for a in triacs or ()),
        *(
            _output("triac", number)
            for number in range(1, TRIAC_COUNT + 1)
            if number not in named_triacs
        ),
        *(
            _output("relay", number, shown=relays is None)
            for number in range(1, RELAY_COUNT + 1)
            if number not in named_relays
        ),
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Ecl310ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ECL output binary sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        supported(
            hass,
            Platform.BINARY_SENSOR,
            [
                *(
                    Ecl310BinarySensor(coordinator, description)
                    for description in binary_sensors(coordinator.device)
                ),
                *(
                    Ecl310HeatAvailable(coordinator, circuit, pump)
                    for circuit in coordinator.device.circuits
                    if (pump := heating_pump(coordinator.device, circuit)) is not None
                ),
            ],
        )
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
        value = getattr(self._subsystem, self.entity_description.field)
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


def heating_pump(device: Ecl310, circuit: Circuit) -> int | None:
    """Return the relay of a heating circuit's pump, if the application names it."""
    if circuit.kind != COMPONENT_HEATING:
        return None
    for assignment in device.relay_assignments or ():
        base, _ = role_name(assignment.key)
        if base.removesuffix("_circuit") != "heating_pump":
            continue
        if role_circuit(assignment.key) in (None, circuit.number):
            return assignment.number
    return None


class Ecl310HeatAvailable(Ecl310Entity, BinarySensorEntity):
    """Whether the heating circuit is supplying heat - for radiator valves."""

    _attr_translation_key = "heat_available"
    # No device class: "heat" would read hot/normal; the states are translated.
    _attr_icon = "mdi:fire-circle"

    def __init__(
        self, coordinator: Ecl310Coordinator, circuit: Circuit, pump_relay: int
    ) -> None:
        """Initialize the sensor on the heating circuit's device."""
        super().__init__(
            coordinator,
            circuit_key("heat_available", circuit),
            circuit.component,
            ("mode", "state"),
        )
        self._pump_field = f"relay_{pump_relay}"
        self._extra_datapoints = ((COMPONENT_OUTPUTS, self._pump_field),)

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
        circuit = self._subsystem
        return heat_available(
            getattr(circuit, "mode", None),
            getattr(circuit, "state", None),
            getattr(self.coordinator.device.outputs, self._pump_field),
        )
