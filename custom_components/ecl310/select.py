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

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import COMPONENT_HEATING, COMPONENT_HOT_WATER, COMPONENT_OUTPUTS
from .coordinator import Ecl310ConfigEntry, Ecl310Coordinator
from .ecl310_modbus import Circuit, Ecl310, OutputControl
from .entity import Ecl310Entity, circuit_key, role_name, supported

PARALLEL_UPDATES = 1
PARALLEL_FULL_ON = 100
PARALLEL_MAX_THRESHOLD = 99

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
                    Ecl310ActuatorType(coordinator, circuit)
                    for circuit in coordinator.device.circuits
                ),
                *(
                    Ecl310AlarmInputPolarity(coordinator, circuit)
                    for circuit in coordinator.device.circuits
                    if circuit.kind == COMPONENT_HEATING
                ),
            ],
        )
    )


class Ecl310AlarmInputPolarity(Ecl310Entity, SelectEntity):
    """Select whether contact closure or opening activates the alarm."""

    _attr_translation_key = "alarm_input_polarity"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_options = ["closed", "open"]

    def __init__(self, coordinator: Ecl310Coordinator, circuit: Circuit) -> None:
        """Attach the input to its heating circuit."""
        super().__init__(
            coordinator,
            circuit_key("alarm_input_polarity", circuit),
            circuit.component,
            ("alarm_input_polarity",),
        )

    @property
    def current_option(self) -> str | None:
        """Return the contact state which triggers the alarm."""
        value = self._subsystem.alarm_input_polarity
        return None if value is None else self._attr_options[int(value)]

    async def async_select_option(self, option: str) -> None:
        """Write the requested trigger polarity."""
        if option not in self._attr_options:
            message = f"Unsupported alarm input polarity: {option}"
            raise ValueError(message)
        await self._async_write(
            self._subsystem.write("alarm_input_polarity", option == "open")
        )
        await self.coordinator.async_request_refresh()


class Ecl310ActuatorType(Ecl310Entity, SelectEntity):
    """Select thermal ABV (0) or three-point motor (1)."""

    _attr_translation_key = "actuator_type"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_options = ["m_abv", "m_3_point"]

    def __init__(self, coordinator: Ecl310Coordinator, circuit: Circuit) -> None:
        """Attach the actuator to its application circuit."""
        prefix = "hot_water_" if circuit.kind == COMPONENT_HOT_WATER else ""
        super().__init__(
            coordinator,
            circuit_key(f"{prefix}actuator_type", circuit),
            circuit.component,
            ("actuator_type",),
        )

    @property
    def current_option(self) -> str | None:
        """Decode the selector from the controller."""
        value = self._subsystem.actuator_type
        return None if value is None else self._attr_options[int(value)]

    async def async_select_option(self, option: str) -> None:
        """Write an allowed actuator type."""
        if option not in self._attr_options:
            message = f"Unsupported actuator type: {option}"
            raise ValueError(message)
        await self._async_write(
            self._subsystem.write("actuator_type", option == "m_3_point")
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
        self._last_threshold: float | None = None

    async def async_added_to_hass(self) -> None:
        """Recover the most recent conditional threshold."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            self._last_threshold = last.attributes.get("last_threshold")
        self._remember()

    def _remember(self) -> None:
        value = self._subsystem.parallel_operation
        if value is not None and 1 <= value <= PARALLEL_MAX_THRESHOLD:
            self._last_threshold = value

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
            "last_threshold": self._last_threshold,
        }

    async def async_select_option(self, option: str) -> None:
        """Write only a supported mode and refresh the result."""
        if option not in self._attr_options:
            message = f"Unsupported parallel mode: {option}"
            raise ValueError(message)
        self._remember()
        value = {"off": 0, "on": 100, "conditional": self._last_threshold or 1}[option]
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
