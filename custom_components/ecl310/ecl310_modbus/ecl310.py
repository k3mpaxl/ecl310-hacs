"""The top-level device object.

Construct :class:`Ecl310` from a ``modbus_connection.ModbusUnit`` - never from
a connection, and never from a host and port. The consumer owns the link; this
library only reads and writes registers over the unit it is handed, which is
what keeps it usable over any ``modbus-connection`` backend and over the
in-memory mock.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from modbus_connection import (
    ModbusConnectionError,
    ModbusError,
    ModbusTimeoutError,
)

from .applications import PROFILES, ApplicationProfile, Detection, async_detect
from .data_model import Ecl310Component
from .device_info import DeviceInformation
from .subsystems import (
    HeatingCircuit,
    HeatingSchedule,
    HotWater,
    HotWaterSchedule,
    Outputs,
    Sensors,
)
from .system_info import SystemInformation, async_read_system_information

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

    def __init__(
        self, unit: ModbusUnit, application: ApplicationProfile | None = None
    ) -> None:
        """Set up the sub-systems on ``unit``.

        With an ``application``, the sub-systems read only the parameters it
        has: the others are dropped up front instead of being refused by the
        controller one poll at a time. Without one, every parameter this
        library models is read.
        """
        self._unit = unit
        self.application = application
        self.system: SystemInformation | None = None
        self.info = DeviceInformation(
            application=application.title if application else None
        )
        self.sensors = Sensors(unit)
        self.heating = HeatingCircuit(unit)
        self.hot_water = HotWater(unit)
        self.outputs = Outputs(unit)
        self.heating_schedule = HeatingSchedule(unit)
        self.hot_water_schedule = HotWaterSchedule(unit)
        if application is not None:
            for name in ALL_COMPONENT_NAMES:
                component: Ecl310Component = getattr(self, name)
                keep = [
                    field
                    for field in type(component).declared_fields
                    if self._has(component, field)
                ]
                if len(keep) < len(type(component).declared_fields):
                    component.restrict_fields(keep)

    @property
    def modbus_unit(self) -> ModbusUnit:
        """The unit every sub-system reads from and writes to."""
        return self._unit

    def _has(self, component: Ecl310Component, field: str) -> bool:
        """Return whether the application has the parameter behind ``field``."""
        if self.application is None:
            return True
        metadata = component.metadata_for(field)
        if metadata is None or metadata.parameter_id is None:
            return True  # a sensor, mode or output register, not a parameter
        return self.application.has(metadata.parameter_id)

    def supports(self, component: str, field: str) -> bool:
        """Return whether this controller's application has a datapoint.

        Always true without an application: then a datapoint the controller
        does not serve is only found out when it refuses the read.
        """
        return self._has(getattr(self, component), field)

    @staticmethod
    def parameter_ids() -> frozenset[int]:
        """Every ECL parameter this library models."""
        ids: set[int] = set()
        for component_type in (
            Sensors,
            HeatingCircuit,
            HotWater,
            Outputs,
            HeatingSchedule,
            HotWaterSchedule,
        ):
            for descriptor in component_type.declared_fields.values():
                metadata = getattr(descriptor, "ecl_metadata", None)
                if metadata is not None and metadata.parameter_id is not None:
                    ids.add(metadata.parameter_id)
        return frozenset(ids)

    async def async_read_system_information(self) -> SystemInformation:
        """Read what the controller reports about itself, into :attr:`info`.

        Read once: none of it changes while the controller runs. The reported
        application replaces the configured one in :attr:`info`; the profile
        the sub-systems read by stays as constructed.
        """
        system = await async_read_system_information(self._unit)
        self.system = system
        self.info = replace(
            self.info,
            application=system.application_title or self.info.application,
            firmware_version=system.software,
            serial_number=system.serial_number,
            hardware_version=system.hardware,
            code_number=system.code_number,
            production=system.production,
        )
        return system

    @classmethod
    async def async_detect_application(
        cls,
        unit: ModbusUnit,
        profiles: tuple[ApplicationProfile, ...] | None = None,
    ) -> Detection:
        """Find out which of the known applications the controller runs.

        Asks the controller first (PNU 2060-2063). One that does not say is
        probed: a handful of parameters that tell the applications apart are
        read one by one. ``Detection.application`` is the answer when clear.
        """
        candidates = tuple(PROFILES.values() if profiles is None else profiles)
        system = await async_read_system_information(unit)
        if system.application_title is not None:
            profile = next((p for p in candidates if p.key == system.profile_key), None)
            return Detection(
                frozenset(),
                frozenset(),
                (),
                reported=system.application_title,
                reported_profile=profile,
            )
        return await async_detect(unit, candidates, preferred=cls.parameter_ids())

    @classmethod
    async def async_probe(cls, unit: ModbusUnit) -> DeviceInformation:
        """Check that a controller answers on ``unit`` and describe it.

        Raises the ``ModbusError`` subclass for the condition when the device
        is unreachable or refuses the read, so a caller validating user input
        can turn that into "cannot connect".
        """
        device = cls(unit)
        # The sensor inputs: unlike most parameters, every application has them.
        await device.sensors.async_update()
        await device.async_read_system_information()
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
