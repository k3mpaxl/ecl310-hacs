"""Select platform - forcing a pump output.

A relay's state register is a result and the controller refuses a write to it.
What can be written is the relay's *override* register, and it has three
positions rather than two: hand the output back to the controller's own
regulation, hold it off, or hold it on. That is a select, not a switch.

An override holds until it is released - nothing times it out. And an operator
standing at the ECL outranks Modbus: while an output is in manual mode at the
controller's own display, the override register says what was asked for rather
than what the output is doing, which is what the matching diagnostic sensor is
for.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import COMPONENT_OUTPUTS
from .coordinator import Ecl310ConfigEntry, Ecl310Coordinator
from .ecl310_modbus import OutputControl
from .ecl310_modbus.configurations import RELAY_ASSIGNMENTS
from .entity import Ecl310Entity

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


SELECTS: tuple[Ecl310SelectDescription, ...] = tuple(
    Ecl310SelectDescription(
        key=f"{assignment.key}_override",
        translation_key=f"{assignment.key}_override",
        component=COMPONENT_OUTPUTS,
        relay=assignment.number,
    )
    for assignment in RELAY_ASSIGNMENTS
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: Ecl310ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ECL relay overrides."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        Ecl310Select(coordinator, description) for description in SELECTS
    )


class Ecl310Select(Ecl310Entity, SelectEntity):
    """One relay override."""

    entity_description: Ecl310SelectDescription
    _attr_options = list(OPTIONS)

    def __init__(
        self, coordinator: Ecl310Coordinator, description: Ecl310SelectDescription
    ) -> None:
        """Initialize the select."""
        super().__init__(coordinator, description.key, description.component)
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
        await self.coordinator.device.outputs.async_set_relay_override(
            self.entity_description.relay, OPTIONS[option]
        )
        await self.coordinator.async_request_refresh()
