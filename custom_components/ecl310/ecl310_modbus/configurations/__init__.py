"""Static configuration tables: readable address ranges and I/O assignments."""

from .address_ranges import COIL_RANGES, REGISTER_RANGES, is_span_readable
from .output_assignments import (
    RELAY_ASSIGNMENTS,
    RELAY_ASSIGNMENTS_BY_KEY,
    RELAY_ASSIGNMENTS_BY_NUMBER,
    OutputAssignment,
)
from .sensor_assignments import SENSOR_ASSIGNMENTS, SensorAssignment

__all__ = [
    "COIL_RANGES",
    "REGISTER_RANGES",
    "RELAY_ASSIGNMENTS",
    "RELAY_ASSIGNMENTS_BY_KEY",
    "RELAY_ASSIGNMENTS_BY_NUMBER",
    "OutputAssignment",
    "SENSOR_ASSIGNMENTS",
    "SensorAssignment",
    "is_span_readable",
]
