"""Data update coordinator polling the ECL controller."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from modbus_connection import (
    IllegalDataAddressError,
    IllegalFunctionError,
    ModbusError,
)

from .const import DOMAIN, LOGGER, SCAN_INTERVAL, SCHEDULE_REFRESH_EVERY
from .ecl310_modbus import SCHEDULE_COMPONENT_NAMES, Ecl310, UpdateReport

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from homeassistant.core import HomeAssistant
    from modbus_connection import ModbusUnit

    from .data import Ecl310Data

    type Ecl310ConfigEntry = ConfigEntry[Ecl310Data]
else:
    Ecl310ConfigEntry = ConfigEntry

#: What a controller answers for a register its application does not serve.
REFUSED_ERRORS = (IllegalDataAddressError, IllegalFunctionError)


def _reader(
    unit: ModbusUnit, space: str
) -> Callable[[int, int], Awaitable[Sequence[int | bool]]]:
    """Return the unit's read call for one address space."""
    return {
        "holding": unit.read_holding_registers,
        "input": unit.read_input_registers,
        "coil": unit.read_coils,
        "discrete": unit.read_discrete_inputs,
    }[space]


class Ecl310Coordinator(DataUpdateCoordinator[UpdateReport]):
    """Refresh every sub-system on a schedule.

    ``Ecl310.async_update`` reads each sub-system on its own and returns an
    ``UpdateReport`` naming the ones that answered, so a controller that
    refuses one block keeps the rest of its entities alive.

    Controllers differ in which parameters their application serves, and one
    register the controller does not have fails the whole block it is read
    in. So when a sub-system is refused, the registers it covers are tried one
    by one; those the controller refuses are logged, dropped from the
    sub-system for as long as the entry is loaded, and the entities reading
    them stay unavailable. The rest of the sub-system carries on.

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
        self._refused: dict[str, frozenset[str]] = {}
        #: Held across a read-modify-write of a register that packs several
        #: entities' values, such as the anti-bacteria weekday mask.
        self.mask_lock = asyncio.Lock()

    def answered(self, component: str) -> bool:
        """Return whether a sub-system's last read succeeded.

        The weekly programs are not in every poll, so their entities cannot
        take their availability from the latest report the way the others do.
        """
        if component in SCHEDULE_COMPONENT_NAMES:
            return component in self._schedules
        return self.data is not None and component in self.data.updated

    def refused(self, component: str) -> frozenset[str]:
        """Return the fields of a sub-system the controller does not serve."""
        return self._refused.get(component, frozenset())

    async def _async_drop_refused(self, name: str, err: ModbusError) -> bool:
        """Drop the fields of a refused block the controller does not serve.

        Returns whether anything was dropped, which is what makes another read
        of the sub-system worth trying.
        """
        block = getattr(err, "block", None)
        if not isinstance(err, REFUSED_ERRORS) or block is None:
            return False
        component = getattr(self.device, name)
        fields = component.resolved_fields
        covered = [
            field
            for field, where in fields.items()
            if where.space == block.space
            and where.address < block.address + block.count
            and block.address < where.address + where.count
        ]
        if len(covered) == 1:
            refused = covered
        else:
            refused = []
            for field in covered:
                where = fields[field]
                try:
                    await _reader(self.device.modbus_unit, where.space)(
                        where.address, where.count
                    )
                except REFUSED_ERRORS:
                    refused.append(field)
        if not refused:
            return False

        for field in refused:
            LOGGER.warning(
                "The controller does not serve %s register %d (%s.%s); "
                "the entity reading it stays unavailable",
                fields[field].space,
                fields[field].address,
                name,
                field,
            )
        component.restrict_fields(set(fields) - set(refused))
        self._refused[name] = self.refused(name) | set(refused)
        return True

    async def _async_recover(self, report: UpdateReport) -> None:
        """Re-read each refused sub-system without the registers it lacks."""
        for name, err in list(report.failed.items()):
            error: ModbusError = err
            while await self._async_drop_refused(name, error):
                try:
                    await getattr(self.device, name).async_update(notify=False)
                except ModbusError as retry_err:
                    error = retry_err
                else:
                    del report.failed[name]
                    report.updated.append(name)
                    break
            else:
                report.failed[name] = error

    async def async_refresh_schedules(self) -> None:
        """Re-read the weekly programs, then publish the new values.

        Called after a program is written, so the entity shows what the
        controller took rather than waiting for the slow cadence to come
        round.
        """
        report = await self.device.async_update_schedules()
        await self._async_recover(report)
        self._schedules = frozenset(report.updated)
        self.async_update_listeners()

    async def _async_update_data(self) -> UpdateReport:
        """Poll the controller and report which sub-systems answered."""
        schedules = self._polls % SCHEDULE_REFRESH_EVERY == 0
        self._polls += 1
        try:
            report = await self.device.async_update(schedules=schedules)
            await self._async_recover(report)
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
