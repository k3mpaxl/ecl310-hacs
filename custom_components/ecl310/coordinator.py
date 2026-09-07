"""Data update coordinator polling the ECL controller."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from modbus_connection import ModbusError

from .const import DOMAIN, LOGGER, SCAN_INTERVAL, SCHEDULE_REFRESH_EVERY
from .ecl310_modbus import SCHEDULE_COMPONENT_NAMES, Ecl310, UpdateReport

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import Ecl310Data

    type Ecl310ConfigEntry = ConfigEntry[Ecl310Data]
else:
    Ecl310ConfigEntry = ConfigEntry


class Ecl310Coordinator(DataUpdateCoordinator[UpdateReport]):
    """Refresh every sub-system on a schedule.

    ``Ecl310.async_update`` reads each sub-system on its own and returns an
    ``UpdateReport`` naming the ones that answered, so a controller that
    refuses one block keeps the rest of its entities alive.

    The weekly programs are read on the first poll and every tenth after it.
    They are fourteen block reads of their own - the registers between two
    weekdays are not served - for values only an operator changes.
    """

    config_entry: Ecl310ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: Ecl310ConfigEntry,
        device: Ecl310,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=SCAN_INTERVAL,
        )
        self.device = device
        self._failed: frozenset[str] = frozenset()
        self._polls = 0
        self._schedules: frozenset[str] = frozenset()

    def answered(self, component: str) -> bool:
        """Return whether a sub-system's last read succeeded.

        The weekly programs are not in every poll, so their entities cannot
        take their availability from the latest report the way the others do.
        """
        if component in SCHEDULE_COMPONENT_NAMES:
            return component in self._schedules
        return self.data is not None and component in self.data.updated

    async def async_refresh_schedules(self) -> None:
        """Re-read the weekly programs, then publish the new values.

        Called after a program is written, so the entity shows what the
        controller took rather than waiting for the slow cadence to come
        round.
        """
        report = await self.device.async_update_schedules()
        self._schedules = frozenset(report.updated)
        self.async_update_listeners()

    async def _async_update_data(self) -> UpdateReport:
        """Poll the controller and report which sub-systems answered."""
        schedules = self._polls % SCHEDULE_REFRESH_EVERY == 0
        self._polls += 1
        try:
            report = await self.device.async_update(schedules=schedules)
        except ModbusError as err:
            message = f"Error communicating with the controller: {err}"
            raise UpdateFailed(message) from err

        if not report.updated:
            errors = list(report.failed.values())
            message = f"No sub-system answered: {errors[0]}"
            raise UpdateFailed(message)

        for name in sorted(report.failed.keys() - self._failed):
            LOGGER.warning("Failed to fetch %s: %s", name, report.failed[name])
        self._failed = frozenset(report.failed)
        if schedules:
            self._schedules = frozenset(
                name for name in report.updated if name in SCHEDULE_COMPONENT_NAMES
            )
        return report
