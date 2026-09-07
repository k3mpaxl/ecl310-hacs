"""Switch platform - the settings that really are two-valued.

Forcing a pump looks like a switch but is not one: the controller's override
register has three positions, the third being "hand it back to the
regulation", so the pumps are on the select platform instead.

The anti-bacteria weekdays are one register holding a seven-bit mask, which is
seven switches here. Writing one reads the others back off the controller's
last value, so two changes in the same second could lose one; in practice a
weekday is set once and left alone.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import COMPONENT_HEATING, COMPONENT_HOT_WATER
from .coordinator import Ecl310ConfigEntry, Ecl310Coordinator
from .ecl310_modbus import Ecl310, HeatingCircuit, HotWater
from .ecl310_modbus.enums import Weekday
from .entity import Ecl310Entity

PARALLEL_UPDATES = 1

#: The attribute-name fragment each weekday is exposed under.
WEEKDAY_KEYS: tuple[str, ...] = tuple(day.name.lower() for day in Weekday)


@dataclass(frozen=True, kw_only=True)
class Ecl310SwitchDescription(SwitchEntityDescription):
    """Describes a switch reading and writing one datapoint."""

    component: str
    value_fn: Callable[[Ecl310], bool | None]
    set_fn: Callable[[Ecl310, bool], Awaitable[None]]


def _disinfection_day(day: int) -> Ecl310SwitchDescription:
    """Describe one weekday of the anti-bacteria run."""
    name = WEEKDAY_KEYS[day]
    return Ecl310SwitchDescription(
        key=f"disinfection_{name}",
        translation_key=f"disinfection_{name}",
        component=COMPONENT_HOT_WATER,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda device, index=day: _day_is_set(device, index),
        set_fn=lambda device, on, index=day: _set_day(device, index, on=on),
    )


def _day_is_set(device: Ecl310, day: int) -> bool | None:
    """Return whether the anti-bacteria run covers one weekday."""
    days = device.hot_water.disinfection_weekdays
    return None if days is None else day in days


async def _set_day(device: Ecl310, day: int, *, on: bool) -> None:
    """Add or remove one weekday from the anti-bacteria run."""
    water = cast(HotWater, device.hot_water)
    days = set(water.disinfection_weekdays or ())
    days.add(day) if on else days.discard(day)
    await water.async_set_disinfection_weekdays(sorted(days))


SWITCHES: tuple[Ecl310SwitchDescription, ...] = (
    Ecl310SwitchDescription(
        key="pump_off_in_setback",
        translation_key="pump_off_in_setback",
        component=COMPONENT_HEATING,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda device: device.heating.pump_off_in_setback,
        set_fn=lambda device, on: cast(
            HeatingCircuit, device.heating
        ).async_set_pump_off_in_setback(on),
    ),
    Ecl310SwitchDescription(
        key="hot_water_priority",
        translation_key="hot_water_priority",
        component=COMPONENT_HEATING,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda device: device.heating.hot_water_priority,
        set_fn=lambda device, on: cast(
            HeatingCircuit, device.heating
        ).async_set_hot_water_priority(on),
    ),
    *(_disinfection_day(day) for day in range(7)),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: Ecl310ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ECL switches."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        Ecl310Switch(coordinator, description) for description in SWITCHES
    )


class Ecl310Switch(Ecl310Entity, SwitchEntity):
    """One on/off datapoint."""

    entity_description: Ecl310SwitchDescription

    def __init__(
        self, coordinator: Ecl310Coordinator, description: Ecl310SwitchDescription
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, description.key, description.component)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return whether the datapoint is on."""
        return self.entity_description.value_fn(self.coordinator.device)

    async def async_turn_on(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Switch it on."""
        await self._async_set(on=True)

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Switch it off."""
        await self._async_set(on=False)

    async def _async_set(self, *, on: bool) -> None:
        """Write the value and refresh so the state reflects the controller."""
        await self.entity_description.set_fn(self.coordinator.device, on)
        await self.coordinator.async_request_refresh()
