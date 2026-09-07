"""The weekly programs (ECL "Zeitplan").

Each control circuit has one, and each holds three comfort periods per weekday.
A period is a pair of registers, both an ``HHMM`` integer: ``600`` is 06:00,
``2030`` is 20:30, ``2400`` is the end of the day. Between the start of a
period and its stop the circuit runs at its comfort setpoint; outside them, at
its setback setpoint.

The registers are laid out on a stride of ten per day, of which six are used::

    3110 + 10 * day + 2 * (period - 1)      ON   (ECL parameter numbering)
    3110 + 10 * day + 2 * (period - 1) + 1  OFF

The four registers between one day and the next are **not served** - a read
that spans them is refused - so a schedule costs one block read per weekday.
They change rarely, which is what makes that affordable.

A period with equal start and stop is off. The controller's own default for an
unused period is ``2400``/``2400``, but any zero-length pair means the same
thing, and an ECL that has been configured by hand often carries something
else - ``2330``/``2330`` on this installation.
"""

from __future__ import annotations

from modbus_connection.model import NumberField

from ..addresses import (
    END_OF_DAY,
    PERIODS,
    field_name,
    is_valid_time,
    parameter_address,
    period_parameter,
)
from ..data_model import Ecl310Component, register_integer
from ..enums import Weekday
from ..exceptions import Ecl310ValueValidationError


def _boundary(
    circuit: int, day: Weekday, period: int, *, stop: bool
) -> NumberField[int]:
    """Declare one period boundary register."""
    parameter = period_parameter(circuit, day, period, stop=stop)
    edge = "Ende" if stop else "Beginn"
    return register_integer(
        parameter_address(parameter),
        signed=False,
        min_value=0,
        max_value=END_OF_DAY,
        digits=0,
        parameter_id=parameter,
        maker_key=f"{day.name.title()} P{period} {'OFF' if stop else 'ON'}",
        maker_category="schedule",
        description=(
            f"{edge} des {period}. Komfortzeitraums am {day.name.title()} (HHMM)"
        ),
        writable=True,
    )


class Schedule(Ecl310Component):
    """One circuit's weekly program.

    Subclassed per circuit rather than parameterised, because a component's
    fields are class attributes: the register addresses have to be fixed by the
    time the class exists.
    """

    #: The ECL circuit this schedule belongs to. Set by each subclass.
    CIRCUIT: int = 0

    def _field(self, day: Weekday | int, period: int, *, stop: bool) -> int | None:
        value = getattr(self, field_name(day, period, stop=stop))
        return None if value is None else int(value)

    def period(self, day: Weekday | int, period: int) -> tuple[int, int] | None:
        """Return one period as ``(start, stop)`` in ``HHMM``."""
        if not 1 <= period <= PERIODS:
            raise Ecl310ValueValidationError(
                f"Expected a period 1..{PERIODS}, got {period}"
            )
        start = self._field(day, period, stop=False)
        end = self._field(day, period, stop=True)
        if start is None or end is None:
            return None
        return (start, end)

    def day(self, day: Weekday | int) -> tuple[tuple[int, int] | None, ...]:
        """Return all three periods of one weekday."""
        return tuple(self.period(day, period) for period in range(1, PERIODS + 1))

    @property
    def week(self) -> dict[Weekday, tuple[tuple[int, int] | None, ...]]:
        """The whole week, keyed by weekday."""
        return {weekday: self.day(weekday) for weekday in Weekday}

    def is_active_period(self, day: Weekday | int, period: int) -> bool | None:
        """Return whether a period covers any time at all."""
        window = self.period(day, period)
        if window is None:
            return None
        return window[0] != window[1]

    async def async_set_boundary(
        self, day: Weekday | int, period: int, value: int, *, stop: bool
    ) -> None:
        """Write one period boundary as an ``HHMM`` value."""
        if not is_valid_time(value):
            raise Ecl310ValueValidationError(
                f"Expected an HHMM time of day up to {END_OF_DAY}, got {value}"
            )
        await self.write(field_name(day, period, stop=stop), value)

    async def async_set_period(
        self, day: Weekday | int, period: int, start: int, stop: int
    ) -> None:
        """Write both boundaries of one period.

        The start is written first, so a controller that validates the pair
        never sees a window that ends before it begins - unless the new start
        is later than the old stop, which is why an inverted result is refused
        here rather than at the register.
        """
        if start > stop:
            raise Ecl310ValueValidationError(
                f"A period cannot end before it starts, got {start} to {stop}"
            )
        await self.async_set_boundary(day, period, stop, stop=True)
        await self.async_set_boundary(day, period, start, stop=False)


def _build(name: str, circuit: int) -> type[Schedule]:
    """Create the schedule component for one circuit."""
    namespace: dict[str, object] = {
        "CIRCUIT": circuit,
        "__doc__": f"The weekly program of ECL circuit {circuit}.",
    }
    for day in Weekday:
        for period in range(1, PERIODS + 1):
            for stop in (False, True):
                namespace[field_name(day, period, stop=stop)] = _boundary(
                    circuit, day, period, stop=stop
                )
    return type(name, (Schedule,), namespace)


HeatingSchedule = _build("HeatingSchedule", 1)
HotWaterSchedule = _build("HotWaterSchedule", 2)
