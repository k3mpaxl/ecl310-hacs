"""Select platform - forcing a pump output.

A relay's state register is a result and the controller refuses a write to it.
What can be written is the relay's *override* register, and it has three
positions rather than two: hand the output back to the controller's own
regulation, hold it off, or hold it on. That is a select, not a switch.

An override holds until it is released - nothing times it out. And an operator
standing at the ECL outranks Modbus: while an output is in manual mode at the
controller's own display, the override register says what was asked for rather
than what the output is doing. The library reads those manual registers and the
diagnostics download carries them, which is where to look if an override seems
to do nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    COMPONENT_HEATING,
    COMPONENT_HOT_WATER,
    COMPONENT_OUTPUTS,
    PARALLEL_FULL_ON,
    PARALLEL_MAX_THRESHOLD,
)
from .coordinator import Ecl310ConfigEntry, Ecl310Coordinator
from .ecl310_modbus import Circuit, Ecl310, HotWater, OutputControl
from .entity import Ecl310Entity, circuit_key, role_name, supported

PARALLEL_UPDATES = 1

#: The override positions, as the option strings Home Assistant shows.
OPTIONS: dict[str, OutputControl] = {
    control.name.lower(): control for control in OutputControl
}


@dataclass(frozen=True, kw_only=True)
class Ecl310SelectDescription(SelectEntityDescription):
    """Describes a select reading and writing one relay override."""

    component: str
    relay: int


def selects(device: Ecl310) -> tuple[Ecl310SelectDescription, ...]:
    """Describe an override for each pump the application names."""
    descriptions = []
    for assignment in device.relay_assignments or ():
        translation_key, placeholders = role_name(f"{assignment.key}_override")
        descriptions.append(
            Ecl310SelectDescription(
                key=f"{assignment.key}_override",
                translation_key=translation_key,
                translation_placeholders=placeholders,
                component=COMPONENT_OUTPUTS,
                relay=assignment.number,
            )
        )
    return tuple(descriptions)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Ecl310ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ECL relay overrides."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        supported(
            hass,
            Platform.SELECT,
            [
                *(
                    Ecl310Select(coordinator, description)
                    for description in selects(coordinator.device)
                ),
                *(
                    Ecl310ParallelMode(coordinator, circuit)
                    for circuit in coordinator.device.circuits
                    if circuit.kind == COMPONENT_HEATING
                ),
                *(
                    Ecl310OptimisationBasis(coordinator, circuit)
                    for circuit in coordinator.device.circuits
                    if circuit.kind == COMPONENT_HEATING
                ),
                *(
                    Ecl310ActuatorType(coordinator, circuit)
                    for circuit in coordinator.device.circuits
                ),
                *(
                    Ecl310DisinfectionStart(coordinator, circuit)
                    for circuit in coordinator.device.circuits
                    if circuit.kind == COMPONENT_HOT_WATER
                ),
            ],
        )
    )


class Ecl310ActuatorType(Ecl310Entity, SelectEntity):
    """The kind of actuator that moves a circuit's control valve.

    It decides how the controller drives the valve. A gear motor gets short
    open and close pulses (3-point control), which motor protection, Xp, Tn,
    running time, neutral zone and minimum pulse tune. A thermal actuator
    (Danfoss M-ABV) gets a pulse-width signal and ignores those settings.
    """

    _attr_translation_key = "actuator_type"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_options = ["thermal", "gear_motor"]

    def __init__(self, coordinator: Ecl310Coordinator, circuit: Circuit) -> None:
        """Attach the actuator type to its circuit."""
        key = (
            "hot_water_actuator_type"
            if circuit.kind == COMPONENT_HOT_WATER
            else "actuator_type"
        )
        super().__init__(
            coordinator,
            circuit_key(key, circuit),
            circuit.component,
            ("actuator_type",),
        )

    @property
    def current_option(self) -> str | None:
        """Return the actuator type the controller drives."""
        value = self._subsystem.actuator_type
        if value is None:
            return None
        return "gear_motor" if value else "thermal"

    async def async_select_option(self, option: str) -> None:
        """Tell the controller which actuator it drives."""
        await self._async_write(
            self._subsystem.write("actuator_type", option == "gear_motor")
        )
        await self.coordinator.async_request_refresh()


class Ecl310OptimisationBasis(Ecl310Entity, SelectEntity):
    """Whether optimised start and stop follow the outdoor or the room temperature.

    The room temperature only counts where the controller measures it.
    """

    _attr_translation_key = "optimisation_basis"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_options = ["outdoor", "room"]

    def __init__(self, coordinator: Ecl310Coordinator, circuit: Circuit) -> None:
        """Attach the setting to its heating circuit."""
        super().__init__(
            coordinator,
            circuit_key("optimisation_basis", circuit),
            circuit.component,
            ("optimisation_basis",),
        )

    @property
    def current_option(self) -> str | None:
        """Return what the optimisation follows."""
        value = self._subsystem.optimisation_basis
        if value is None:
            return None
        return "room" if value else "outdoor"

    async def async_select_option(self, option: str) -> None:
        """Choose what the optimisation follows."""
        await self._async_write(
            self._subsystem.write("optimisation_basis", option == "room")
        )
        await self.coordinator.async_request_refresh()


class Ecl310DisinfectionStart(Ecl310Entity, SelectEntity):
    """When the anti-bacteria run starts.

    The controller counts it in half-hour slots from midnight, so it is offered
    as the 48 half hours of the day and nothing in between.
    """

    _attr_translation_key = "disinfection_start"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = [
        f"{hour:02d}:{minute:02d}" for hour in range(24) for minute in (0, 30)
    ]

    def __init__(self, coordinator: Ecl310Coordinator, circuit: Circuit) -> None:
        """Attach the start to its hot water circuit."""
        super().__init__(
            coordinator,
            circuit_key("disinfection_start", circuit),
            circuit.component,
            ("disinfection_start",),
        )

    @property
    def _water(self) -> HotWater:
        return cast(HotWater, self._subsystem)

    @property
    def current_option(self) -> str | None:
        """Return the start of the anti-bacteria run."""
        start = self._water.disinfection_start_time
        return None if start is None else f"{start[0]:02d}:{start[1]:02d}"

    async def async_select_option(self, option: str) -> None:
        """Write the start."""
        hour, minute = (int(part) for part in option.split(":"))
        await self._async_write(
            self._water.async_set_disinfection_start_time(hour, minute)
        )
        await self.coordinator.async_request_refresh()


class Ecl310ParallelMode(Ecl310Entity, SelectEntity, RestoreEntity):
    """Expose OFF, conditional operation and supported full ON mode."""

    _attr_translation_key = "parallel_operation_mode"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: Ecl310Coordinator, circuit: Circuit) -> None:
        """Attach the mode to its heating circuit."""
        super().__init__(
            coordinator,
            circuit_key("parallel_operation_mode", circuit),
            circuit.component,
            ("parallel_operation",),
        )
        number = self._metadata("parallel_operation").number
        self._attr_options = ["off", "conditional"]
        if (
            number is not None
            and number.max_value is not None
            and number.max_value >= PARALLEL_FULL_ON
        ):
            self._attr_options.append("on")

    async def async_added_to_hass(self) -> None:
        """Recover the most recent conditional threshold."""
        await super().async_added_to_hass()
        memory = self.coordinator.memory
        if (
            memory.get(self._component, "parallel_operation") is None
            and (last := await self.async_get_last_state()) is not None
            and isinstance(last.attributes.get("last_threshold"), int | float)
        ):
            memory.remember(
                self._component, "parallel_operation", last.attributes["last_threshold"]
            )
        self._remember()

    def _remember(self) -> None:
        value = self._subsystem.parallel_operation
        if value is not None and 1 <= value <= PARALLEL_MAX_THRESHOLD:
            self.coordinator.memory.remember(self._component, "parallel_operation", value)

    def _handle_coordinator_update(self) -> None:
        self._remember()
        super()._handle_coordinator_update()

    @property
    def current_option(self) -> str | None:
        """Decode the ECL's special values."""
        value = self._subsystem.parallel_operation
        if value is None:
            return None
        if value == 0:
            return "off"
        if value == PARALLEL_FULL_ON:
            return "on" if "on" in self._attr_options else None
        return "conditional" if 1 <= value <= PARALLEL_MAX_THRESHOLD else None

    @property
    def extra_state_attributes(self) -> dict:
        """Expose the last threshold and PNU."""
        return {
            **(super().extra_state_attributes or {}),
            "last_threshold": self.coordinator.memory.get(
                self._component, "parallel_operation"
            ),
        }

    async def async_select_option(self, option: str) -> None:
        """Write only a supported mode and refresh the result."""
        if option not in self._attr_options:
            message = f"Unsupported parallel mode: {option}"
            raise ValueError(message)
        self._remember()
        threshold = self.coordinator.memory.get(self._component, "parallel_operation")
        value = {"off": 0, "on": 100, "conditional": threshold or 1}[option]
        await self._async_write(self._subsystem.write("parallel_operation", value))
        await self.coordinator.async_request_refresh()


class Ecl310Select(Ecl310Entity, SelectEntity):
    """One relay override."""

    entity_description: Ecl310SelectDescription
    _attr_options = list(OPTIONS)

    def __init__(
        self, coordinator: Ecl310Coordinator, description: Ecl310SelectDescription
    ) -> None:
        """Initialize the select."""
        super().__init__(
            coordinator,
            description.key,
            description.component,
            (f"relay_{description.relay}_override",),
        )
        self.entity_description = description

    @property
    def current_option(self) -> str | None:
        """Return what the relay is currently overridden to."""
        control = self.coordinator.device.outputs.relay_override(
            self.entity_description.relay
        )
        return None if control is None else control.name.lower()

    async def async_select_option(self, option: str) -> None:
        """Write the override, then refresh so the state follows the device."""
        await self._async_write(
            self.coordinator.device.outputs.async_set_relay_override(
                self.entity_description.relay, OPTIONS[option]
            )
        )
        await self.coordinator.async_request_refresh()
