"""Time platform - the weekly programs.

Each control circuit keeps three comfort periods per weekday, and each period
is a start and a stop. That is 42 entities per circuit, 84 in all, which is a
lot of entities - but it is what a weekly program is, and Home Assistant has
no entity that carries one whole.

Only the first period of each day is enabled by default. The controller stores
an unused period as a zero-length one, so periods 2 and 3 usually read the same
value twice; enable them on the days you actually use them.

The registers hold ``HHMM`` and go up to ``2400``, which ``datetime.time``
cannot express. A register reading ``2400`` is shown as 23:59, and stays
``2400`` in the controller until someone sets that entity - at which point the
time they picked is what gets written.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import cast

from homeassistant.components.time import TimeEntity, TimeEntityDescription
from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    COMPONENT_HEATING_SCHEDULE,
    COMPONENT_HOT_WATER,
    COMPONENT_HOT_WATER_SCHEDULE,
    DOMAIN,
)
from .coordinator import Ecl310ConfigEntry, Ecl310Coordinator
from .ecl310_modbus import (
    END_OF_DAY,
    PERIODS,
    Schedule,
    Weekday,
    from_hours_minutes,
    to_hours_minutes,
)
from .ecl310_modbus.addresses import field_name
from .entity import Ecl310Entity, circuit_key, per_circuit, supported

PARALLEL_UPDATES = 1

#: The two schedules, by the sub-system they read from.
SCHEDULES: dict[str, str] = {
    COMPONENT_HEATING_SCHEDULE: "heating_schedule",
    COMPONENT_HOT_WATER_SCHEDULE: "hot_water_schedule",
}

#: The last minute a ``datetime.time`` can hold, which is what a register
#: reading 24:00 is shown as.
LAST_MINUTE = time(23, 59)


@dataclass(frozen=True, kw_only=True)
class Ecl310TimeDescription(TimeEntityDescription):
    """Describes one boundary of one comfort period."""

    component: str
    attribute: str
    day: Weekday
    period: int
    stop: bool


def _boundary(
    component: str, day: Weekday, period: int, *, stop: bool
) -> Ecl310TimeDescription:
    """Describe the start or the stop of one comfort period.

    The weekday is part of the translation key rather than a placeholder,
    because a placeholder is substituted verbatim and would leave the day name
    in English whatever the user's language.

    The circuit is part of the *entity* key, because the key is what a unique
    id is built from: the two schedules describe the same 42 boundaries, and
    without it every one of them would collide with its opposite number and
    Home Assistant would drop whichever came second.
    """
    edge = "stop" if stop else "start"
    attribute = field_name(day, period, stop=stop)
    return Ecl310TimeDescription(
        key=f"{component}_{attribute}",
        translation_key=f"{day.name.lower()}_{edge}",
        translation_placeholders={"period": str(period)},
        component=component,
        attribute=attribute,
        day=day,
        period=period,
        stop=stop,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=period == 1,
    )


TIMES: tuple[Ecl310TimeDescription, ...] = tuple(
    _boundary(component, day, period, stop=stop)
    for component in SCHEDULES
    for day in Weekday
    for period in range(1, PERIODS + 1)
    for stop in (False, True)
)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: Ecl310ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the weekly program entities."""
    coordinator = entry.runtime_data.coordinator
    _remove_disinfection_start(hass, entry, coordinator)
    async_add_entities(
        supported(
            hass,
            Platform.TIME,
            (
                Ecl310Time(coordinator, description)
                for description in per_circuit(coordinator.device, TIMES)
            ),
        )
    )


def _remove_disinfection_start(
    hass: HomeAssistant, entry: Ecl310ConfigEntry, coordinator: Ecl310Coordinator
) -> None:
    """Remove the time entity the disinfection start used to be.

    It is a select now, which offers only the half hours the controller counts in.
    """
    registry = er.async_get(hass)
    for circuit in coordinator.device.circuits:
        if circuit.kind != COMPONENT_HOT_WATER:
            continue
        unique_id = f"{entry.entry_id}_{circuit_key('disinfection_start', circuit)}"
        if entity_id := registry.async_get_entity_id(Platform.TIME, DOMAIN, unique_id):
            registry.async_remove(entity_id)


class Ecl310Time(Ecl310Entity, TimeEntity):
    """One boundary of one comfort period."""

    entity_description: Ecl310TimeDescription

    def __init__(
        self, coordinator: Ecl310Coordinator, description: Ecl310TimeDescription
    ) -> None:
        """Initialize the entity."""
        super().__init__(
            coordinator,
            description.key,
            description.component,
            (description.attribute,),
        )
        self.entity_description = description

    @property
    def native_value(self) -> time | None:
        """Return the boundary as a time of day."""
        raw = getattr(self._subsystem, self.entity_description.attribute)
        if raw is None:
            return None
        if raw >= END_OF_DAY:
            return LAST_MINUTE
        hour, minute = to_hours_minutes(int(raw))
        return time(hour, minute)

    async def async_set_value(self, value: time) -> None:
        """Write the boundary, then re-read the program it belongs to."""
        description = self.entity_description
        await self._async_write(
            self._schedule.async_set_boundary(
                description.day,
                description.period,
                from_hours_minutes(value.hour, value.minute),
                stop=description.stop,
            )
        )
        await self.coordinator.async_refresh_schedules()

    @property
    def _schedule(self) -> Schedule:
        """The schedule component this entity writes to."""
        return cast(Schedule, self._subsystem)

