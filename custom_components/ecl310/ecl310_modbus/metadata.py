"""Neutral ECL datapoint metadata.

Every field a component declares carries a :class:`DatapointMetadata` next to
its address, so the model *is* the datasheet: the parameter ID the ECL manual
prints, the value domain the controller accepts, the unit, and whether the
value may be written. Consumers use it to build user interfaces without
hard-coding a second copy of the register map.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Literal

ValueKind = Literal["number", "enum", "boolean"]


@dataclass(frozen=True)
class NumberMetadata:
    """Metadata for numeric ECL values."""

    min_value: float | int | None = None
    max_value: float | int | None = None
    step: float | int | None = None
    digits: int | None = None
    unit: str | None = None
    raw_min: int | None = None
    raw_max: int | None = None


@dataclass(frozen=True)
class OptionMetadata:
    """Metadata for one discrete option."""

    key: str
    value: int
    label: str | None = None


@dataclass(frozen=True)
class EnumMetadata:
    """Metadata for selectable / discrete register values."""

    enum_type: type[IntEnum]
    options: tuple[OptionMetadata, ...]


@dataclass(frozen=True)
class BooleanMetadata:
    """Metadata for on/off values."""

    false_key: str = "off"
    true_key: str = "on"
    inverted: bool = False


@dataclass(frozen=True)
class DatapointMetadata:
    """Neutral metadata for one ECL datapoint."""

    value_kind: ValueKind
    parameter_id: int | None = None
    sensor_number: int | None = None
    maker_key: str | None = None
    maker_category: str | None = None
    description: str | None = None
    writable: bool = False
    number: NumberMetadata | None = None
    enum: EnumMetadata | None = None
    boolean: BooleanMetadata | None = None


def step_from_digits(digits: int | None) -> float | int | None:
    """Return the natural UI/write step from decimal precision."""
    if digits is None:
        return None
    if digits <= 0:
        return 1
    return float(10**-digits)


def attach_metadata[FieldT](field: FieldT, metadata: DatapointMetadata) -> FieldT:
    """Attach ECL metadata to a modbus-connection field."""
    field.ecl_metadata = metadata  # type: ignore[attr-defined]
    return field
