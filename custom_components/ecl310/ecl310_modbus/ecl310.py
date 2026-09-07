"""The top-level device object.

Construct :class:`Ecl310` from a ``modbus_connection.ModbusUnit`` - never from
a connection, and never from a host and port. The consumer owns the link; this
library only reads and writes registers over the unit it is handed, which is
what keeps it usable over any ``modbus-connection`` backend and over the
in-memory mock.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from modbus_connection import (
    ModbusConnectionError,
    ModbusError,
    ModbusTimeoutError,
)

from .device_info import DeviceInformation
from .subsystems import (
    HeatingCircuit,
    HeatingSchedule,
    HotWater,
    HotWaterSchedule,
    Outputs,
    Sensors,
)

if TYPE_CHECKING:
    from modbus_connection import ModbusUnit

#: The controller's factory Modbus station address.
DEFAULT_UNIT_ID = 1

#: The sub-systems an ordinary poll refreshes, in read order.
COMPONENT_NAMES: tuple[str, ...] = ("sensors", "heating", "hot_water", "outputs")

#: The weekly programs. Kept out of the ordinary poll: they cost one block
#: read per weekday each - the registers between two days are not served - and
#: nothing changes them but an operator. Refresh them on their own cadence,
#: and after writing one.
SCHEDULE_COMPONENT_NAMES: tuple[str, ...] = ("heating_schedule", "hot_water_schedule")

#: Everything, for a diagnostics dump.
ALL_COMPONENT_NAMES: tuple[str, ...] = (*COMPONENT_NAMES, *SCHEDULE_COMPONENT_NAMES)


@dataclass
class UpdateReport:
    """What one poll managed to refresh."""

    updated: list[str] = field(default_factory=list)
    """Sub-systems that answered."""

    failed: dict[str, ModbusError] = field(default_factory=dict)
    """Sub-systems that did not, and why."""

    def __bool__(self) -> bool:
        """Whether anything at all was refreshed."""
        return bool(self.updated)


class Ecl310:
    """A Danfoss ECL Comfort 310 reached through a ``ModbusUnit``.

    The controller answers this library's whole register map in a handful of
    short block reads, so there is a single poll rather than one interval per
    category: every sub-system is read on each :meth:`async_update`, each on
    its own so that one refusal does not take the rest with it.
    """

    def __init__(self, unit: ModbusUnit) -> None:
        """Set up the sub-systems on ``unit``."""
        self._unit = unit
        self.info = DeviceInformation()
        self.sensors = Sensors(unit)
        self.heating = HeatingCircuit(unit)
        self.hot_water = HotWater(unit)
        self.outputs = Outputs(unit)
        self.heating_schedule = HeatingSchedule(unit)
        self.hot_water_schedule = HotWaterSchedule(unit)

    @property
    def modbus_unit(self) -> ModbusUnit:
        """The unit every sub-system reads from and writes to."""
        return self._unit

    @classmethod
    async def async_probe(cls, unit: ModbusUnit) -> DeviceInformation:
        """Check that a controller answers on ``unit`` and describe it.

        Raises the ``ModbusError`` subclass for the condition when the device
        is unreachable or refuses the read, so a caller validating user input
        can turn that into "cannot connect".
        """
        device = cls(unit)
        await device.heating.async_update()
        return device.info

    async def _async_poll(
        self, names: tuple[str, ...], report: UpdateReport
    ) -> UpdateReport:
        """Read each named sub-system on its own, recording what happened."""
        for name in names:
            try:
                await getattr(self, name).async_update(notify=False)
            except ModbusConnectionError:
                raise  # the link is down; the rest would only wait for timeouts
            except ModbusTimeoutError as err:
                if not report.updated and not report.failed:
                    raise  # nothing answered yet: assume the rest time out too
                report.failed[name] = err
            except ModbusError as err:
                report.failed[name] = err
            else:
                report.updated.append(name)
        return report

    def _notify(self, report: UpdateReport) -> None:
        """Fire the listeners of everything this update refreshed."""
        for name in report.updated:
            getattr(self, name).notify()

    async def async_update(self, *, schedules: bool = False) -> UpdateReport:
        """Refresh the sub-systems and report what answered.

        The weekly programs are left out unless ``schedules`` asks for them:
        they are fourteen further block reads for values only an operator
        changes.
        """
        names = COMPONENT_NAMES
        if schedules:
            names = (*COMPONENT_NAMES, *SCHEDULE_COMPONENT_NAMES)
        report = await self._async_poll(names, UpdateReport())
        self._notify(report)
        return report

    async def async_update_schedules(self) -> UpdateReport:
        """Refresh only the weekly programs."""
        report = await self._async_poll(SCHEDULE_COMPONENT_NAMES, UpdateReport())
        self._notify(report)
        return report

    async def async_read_raw(self) -> dict[str, dict[int, int | bool]]:
        """Every register this device reads, undecoded - for diagnostics."""
        raw: dict[str, dict[int, int | bool]] = {}
        for name in ALL_COMPONENT_NAMES:
            read = await getattr(self, name).async_read_raw(notify=False)
            for space, values in read.items():
                raw.setdefault(space, {}).update(values)
        return raw
