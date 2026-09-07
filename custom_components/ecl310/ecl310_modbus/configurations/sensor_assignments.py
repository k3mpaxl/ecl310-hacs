"""Which physical input carries which measurement.

An ECL controller's sensor inputs are numbered ``S1``..``S16`` on the terminal
block; what each one measures is decided by the application key installed in
the controller. The assignments below are the ones the A237/A337 family of
applications uses for the inputs this library reads, and they are what the
:class:`~ecl310_modbus.subsystems.sensors.Sensors` component names its
attributes after.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SensorAssignment:
    """One physical input and the measurement it carries."""

    number: int
    """The input's terminal number, ``1`` for ``S1``."""

    key: str
    """The attribute name the sensors component exposes it under."""

    description: str
    """What the input measures, in the manual's wording."""


SENSOR_ASSIGNMENTS: tuple[SensorAssignment, ...] = (
    SensorAssignment(1, "outdoor_temperature", "Außentemperatur (S1)"),
    SensorAssignment(3, "flow_temperature", "Vorlauftemperatur Heizkreis (S3)"),
    SensorAssignment(5, "return_temperature", "Rücklauftemperatur Heizkreis (S5)"),
    SensorAssignment(6, "storage_temperature", "Speichertemperatur Warmwasser (S6)"),
)

SENSOR_ASSIGNMENTS_BY_KEY: dict[str, SensorAssignment] = {
    assignment.key: assignment for assignment in SENSOR_ASSIGNMENTS
}
