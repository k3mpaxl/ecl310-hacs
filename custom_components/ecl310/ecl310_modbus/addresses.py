"""Address helpers for Danfoss ECL parameter and sensor references.

Modbus register addresses are commonly written in two different ways:

-   Protocol addresses start at 0. This is the format expected by most Modbus
    libraries, and the format this package passes to ``modbus-connection``.
-   The Danfoss ECL documentation never mentions register addresses. It labels
    every settable value with a *parameter ID* such as ``11179`` (``Sommer-Aus``)
    or ``12125`` (``Gew. Temp.`` of the disinfection function), and every
    physical input with a *sensor number* such as ``S1``.

The controller exposes ECL parameter *n* at zero-based holding register
``n - 1``, and sensor input ``Sn`` at zero-based holding register
``10199 + n`` (sensors carry parameter IDs of their own: ``Sn`` is parameter
``10200 + n`` in the controller-wide block). Both conversions live here so that
the component definitions can quote the same references the ECL manual and the
controller display use::

    parameter_address(11179)  ->  11178   # Sommer-Aus
    parameter_address(12125)  ->  12124   # disinfection setpoint
    sensor_address(1)         ->  10200   # S1, outdoor temperature
    sensor_address(6)         ->  10205   # S6, hot water storage

The controller serves holding registers only. It answers a coil read (FC01)
with "illegal function", so on/off parameters live in the holding-register
table like everything else, as 0/1.

Circuit-scoped parameters carry the circuit in their leading digits: heating is
circuit 1 (``11xxx``), domestic hot water is circuit 2 (``12xxx``). General
controller values such as the operating mode and the circuit status are not
parameters and are addressed directly.
"""

from __future__ import annotations

from .enums import Weekday
from .exceptions import Ecl310ValueValidationError

PARAMETER_ID_MIN = 1
PARAMETER_ID_MAX = 65536

SENSOR_REGISTER_BASE = 10199
SENSOR_NUMBER_MIN = 1
SENSOR_NUMBER_MAX = 16


def parameter_address(parameter_id: int) -> int:
    """Return the zero-based Modbus address for an ECL parameter ID."""
    if not PARAMETER_ID_MIN <= parameter_id <= PARAMETER_ID_MAX:
        raise ValueError(f"Expected an ECL parameter ID like 11179, got {parameter_id}")
    return parameter_id - 1


def sensor_address(sensor_number: int) -> int:
    """Return the zero-based Modbus address for an ECL sensor input ``Sn``."""
    if not SENSOR_NUMBER_MIN <= sensor_number <= SENSOR_NUMBER_MAX:
        raise ValueError(
            f"Expected an ECL sensor number 1..{SENSOR_NUMBER_MAX}, got {sensor_number}"
        )
    return SENSOR_REGISTER_BASE + sensor_number


def parameter_range(first_id: int, last_id: int) -> tuple[int, int]:
    """Create an inclusive readable register range from two parameter IDs."""
    if last_id < first_id:
        raise ValueError(f"Invalid ECL parameter range: {first_id}..{last_id}")
    return parameter_address(first_id), parameter_address(last_id)


def sensor_range(first_sensor: int, last_sensor: int) -> tuple[int, int]:
    """Create an inclusive readable register range from two sensor numbers."""
    if last_sensor < first_sensor:
        raise ValueError(f"Invalid ECL sensor range: S{first_sensor}..S{last_sensor}")
    return sensor_address(first_sensor), sensor_address(last_sensor)


#: ECL parameter of Monday's first ON time, per circuit.
SCHEDULE_PARAMETERS: dict[int, int] = {1: 3110, 2: 3210}

#: Parameters per weekday, of which the first six carry the three periods.
DAY_STRIDE = 10

#: Comfort periods the controller keeps per day.
PERIODS = 3

#: The largest value a period register takes: 24:00, the end of the day.
END_OF_DAY = 2400


def period_parameter(
    circuit: int, day: Weekday | int, period: int, *, stop: bool
) -> int:
    """Return the ECL parameter of one period boundary."""
    if circuit not in SCHEDULE_PARAMETERS:
        raise Ecl310ValueValidationError(
            f"Expected circuit {sorted(SCHEDULE_PARAMETERS)}, got {circuit}"
        )
    if not 0 <= int(day) <= 6:
        raise Ecl310ValueValidationError(f"Expected a weekday 0..6, got {day}")
    if not 1 <= period <= PERIODS:
        raise Ecl310ValueValidationError(
            f"Expected a period 1..{PERIODS}, got {period}"
        )
    base = SCHEDULE_PARAMETERS[circuit] + DAY_STRIDE * int(day)
    return base + 2 * (period - 1) + (1 if stop else 0)


def day_range(circuit: int, day: Weekday | int) -> tuple[int, int]:
    """Return the readable register block one weekday occupies."""
    first = period_parameter(circuit, day, 1, stop=False)
    last = period_parameter(circuit, day, PERIODS, stop=True)
    return (parameter_address(first), parameter_address(last))


def schedule_ranges(circuit: int) -> tuple[tuple[int, int], ...]:
    """Return the seven blocks one circuit's schedule is read in."""
    return tuple(day_range(circuit, day) for day in Weekday)


def is_valid_time(value: int) -> bool:
    """Return whether ``value`` is an ``HHMM`` the controller accepts."""
    return 0 <= value <= END_OF_DAY and value % 100 < 60


def to_hours_minutes(value: int) -> tuple[int, int]:
    """Split an ``HHMM`` register value into hours and minutes."""
    return divmod(value, 100)


def from_hours_minutes(hour: int, minute: int) -> int:
    """Build an ``HHMM`` register value, ``24:00`` included."""
    value = hour * 100 + minute
    if not is_valid_time(value):
        raise Ecl310ValueValidationError(
            f"Expected a time of day up to 24:00, got {hour:02d}:{minute:02d}"
        )
    return value


def field_name(day: Weekday | int, period: int, *, stop: bool) -> str:
    """Return the attribute name one period boundary is exposed under."""
    return f"{Weekday(day).name.lower()}_p{period}_{'stop' if stop else 'start'}"
