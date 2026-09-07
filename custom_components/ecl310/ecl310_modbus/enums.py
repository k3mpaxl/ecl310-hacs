"""Discrete value domains reported by the controller."""

from __future__ import annotations

from enum import IntEnum


class OperatingMode(IntEnum):
    """The mode a control circuit has been put into.

    Read from the controller's general operating-mode register of the circuit
    (heating: register 4200, hot water: register 4201). It is the value the
    ECL display shows as the circuit's mode symbol.
    """

    MANUAL = 0
    """Manual operation - outputs follow the operator, not the schedule."""

    SCHEDULED = 1
    """Scheduled operation - the circuit follows its weekly program."""

    COMFORT = 2
    """Constant comfort - the comfort setpoint applies around the clock."""

    SETBACK = 3
    """Constant setback - the setback setpoint applies around the clock."""

    FROST_PROTECTION = 4
    """Frost protection - heating is off apart from the frost limit."""


class CircuitState(IntEnum):
    """Where a control circuit currently sits within its schedule.

    Read from the circuit's status register (heating: register 4210, hot water:
    register 4211). It changes on its own as the weekly program advances, and
    it is what distinguishes an already-heating circuit from one that is only
    preparing to.
    """

    SETBACK = 0
    """The setback period is running."""

    PRE_COMFORT = 1
    """Heating up ahead of the next comfort period."""

    COMFORT = 2
    """The comfort period is running."""

    PRE_SETBACK = 3
    """Cooling down ahead of the next setback period."""


class OutputControl(IntEnum):
    """What a switching output is being told to do, outside normal regulation.

    The controller keeps two of these per output. The *manual* register
    (relays: 4025..4030) is what an operator set at the ECL's own display and
    cannot be written over Modbus. The *override* register (relays:
    4065..4070) is the one this library writes.

    They are read together because they are not equal partners: a non-zero
    manual value wins, and while it stands the override register says what was
    asked for rather than what the output is doing.
    """

    AUTO = 0
    """No override - the output follows the controller's own regulation."""

    OFF = 1
    """The output is held off."""

    ON = 2
    """The output is held on."""


class Weekday(IntEnum):
    """A day of the week, numbered as :mod:`datetime` numbers them."""

    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6
