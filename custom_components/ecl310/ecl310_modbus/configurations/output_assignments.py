"""Which switching output drives which pump.

An ECL Comfort 310 has five triac and six relay outputs on its terminal block.
What each one drives is decided by the installed application key and the
wiring, not by the controller, so the outputs are modelled by their terminal
number and named here.

The assignments below are the ones application key A237.1 uses on the
installation this library was developed against. An output with no entry here
is still read and written by terminal number; it just has no name.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OutputAssignment:
    """One switching output and what it drives."""

    number: int
    """The output's terminal number, ``1`` for relay 1."""

    key: str
    """The attribute name the outputs component exposes it under."""

    description: str
    """What the output drives, in the manufacturer's wording."""


RELAY_ASSIGNMENTS: tuple[OutputAssignment, ...] = (
    OutputAssignment(1, "heating_pump", "Heizkreispumpe"),
    OutputAssignment(2, "storage_charge_pump", "Speicherladepumpe"),
    OutputAssignment(3, "circulation_pump", "Zirkulationspumpe"),
)

RELAY_ASSIGNMENTS_BY_KEY: dict[str, OutputAssignment] = {
    assignment.key: assignment for assignment in RELAY_ASSIGNMENTS
}

RELAY_ASSIGNMENTS_BY_NUMBER: dict[int, OutputAssignment] = {
    assignment.number: assignment for assignment in RELAY_ASSIGNMENTS
}
