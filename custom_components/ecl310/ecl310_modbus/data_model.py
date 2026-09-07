"""ECL-specific pieces layered on the ``modbus_connection.model`` framework.

Two things live here:

*   Field helpers that take an **ECL parameter ID** or **sensor number** instead
    of a register address, and attach the neutral
    :mod:`~ecl310_modbus.metadata` describing the datapoint.
*   :class:`Ecl310Component`, the base every sub-system component derives from.
    It carries the controller's readable address ranges and the metadata lookup
    helpers.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import IntEnum
from typing import Any

from modbus_connection.model import (
    Component,
    NumberField,
    boolean as _modbus_boolean,
    enum as _modbus_enum,
    gauge as _modbus_gauge,
    integer as _modbus_integer,
)

from .addresses import parameter_address, sensor_address
from .configurations.address_ranges import COIL_RANGES, REGISTER_RANGES
from .exceptions import Ecl310ValueValidationError
from .metadata import (
    BooleanMetadata,
    DatapointMetadata,
    EnumMetadata,
    NumberMetadata,
    OptionMetadata,
    attach_metadata,
    step_from_digits,
)

#: What a temperature input reports when nothing is connected to it: the top
#: of the documented raw range, 192.00 degrees. Every unused input on a
#: controller reads exactly this, so it decodes to ``None`` rather than to an
#: impossible temperature.
NO_SENSOR_RAW = 19200

#: The widest block read this library asks an ECL controller for. The
#: controller answers up to the Modbus maximum, but a narrow ceiling keeps a
#: refused block small enough to identify from a log line.
MAX_BLOCK_SPAN = 50

#: Registers that are further apart than this are never merged into one read.
MAX_BLOCK_GAP = 16


def _number_validator(
    *,
    min_value: float | int | None,
    max_value: float | int | None,
) -> Callable[[Any], Any]:
    """Return a write validator rejecting values outside the ECL domain."""

    def validate(value: Any) -> Any:
        try:
            number = float(value)
        except (TypeError, ValueError) as err:
            raise Ecl310ValueValidationError(f"{value!r} is not a number") from err
        if min_value is not None and number < min_value:
            raise Ecl310ValueValidationError(
                f"Value {value} is below the minimum {min_value}"
            )
        if max_value is not None and number > max_value:
            raise Ecl310ValueValidationError(
                f"Value {value} is above the maximum {max_value}"
            )
        return value

    return validate


def _writable(
    writable: bool | Callable[[Any], Any],
    *,
    min_value: float | int | None,
    max_value: float | int | None,
) -> bool | Callable[[Any], Any]:
    """Return the ``writable`` argument, validated where a domain is known."""
    if not writable:
        return False
    if callable(writable):
        return writable
    if min_value is None and max_value is None:
        return True
    return _number_validator(min_value=min_value, max_value=max_value)


def _number_metadata(
    *,
    parameter_id: int | None,
    sensor_number: int | None,
    maker_key: str | None,
    maker_category: str | None,
    description: str | None,
    writable: bool | Callable[[Any], Any],
    min_value: float | int | None,
    max_value: float | int | None,
    step: float | int | None,
    digits: int | None,
    unit: str | None,
    raw_min: int | None,
    raw_max: int | None,
) -> DatapointMetadata:
    """Build the neutral metadata for a numeric datapoint."""
    return DatapointMetadata(
        value_kind="number",
        parameter_id=parameter_id,
        sensor_number=sensor_number,
        maker_key=maker_key,
        maker_category=maker_category,
        description=description,
        writable=bool(writable),
        number=NumberMetadata(
            min_value=min_value,
            max_value=max_value,
            step=step if step is not None else step_from_digits(digits),
            digits=digits,
            unit=unit,
            raw_min=raw_min,
            raw_max=raw_max,
        ),
    )


def register_integer(
    address: int,
    *,
    signed: bool = True,
    min_value: float | int | None = None,
    max_value: float | int | None = None,
    step: float | int | None = None,
    digits: int | None = 0,
    unit: str | None = None,
    raw_min: int | None = None,
    raw_max: int | None = None,
    parameter_id: int | None = None,
    sensor_number: int | None = None,
    maker_key: str | None = None,
    maker_category: str | None = None,
    description: str | None = None,
    writable: bool | Callable[[Any], Any] = False,
) -> NumberField[int]:
    """Create an unscaled integer field at a zero-based register address."""
    field: NumberField[int] = _modbus_integer(
        address,
        signed=signed,
        unit=unit,
        writable=_writable(writable, min_value=min_value, max_value=max_value),
    )
    return attach_metadata(
        field,
        _number_metadata(
            parameter_id=parameter_id,
            sensor_number=sensor_number,
            maker_key=maker_key,
            maker_category=maker_category,
            description=description,
            writable=writable,
            min_value=min_value,
            max_value=max_value,
            step=step,
            digits=digits,
            unit=unit,
            raw_min=raw_min,
            raw_max=raw_max,
        ),
    )


def register_gauge(
    address: int,
    scale: float,
    *,
    signed: bool = True,
    nan: int | None = None,
    min_value: float | int | None = None,
    max_value: float | int | None = None,
    step: float | int | None = None,
    digits: int | None = None,
    unit: str | None = None,
    raw_min: int | None = None,
    raw_max: int | None = None,
    parameter_id: int | None = None,
    sensor_number: int | None = None,
    maker_key: str | None = None,
    maker_category: str | None = None,
    description: str | None = None,
    writable: bool | Callable[[Any], Any] = False,
) -> NumberField[float]:
    """Create a scaled numeric field at a zero-based register address."""
    field = _modbus_gauge(
        address,
        scale,
        signed=signed,
        nan=nan,
        unit=unit,
        writable=_writable(writable, min_value=min_value, max_value=max_value),
    )
    return attach_metadata(
        field,
        _number_metadata(
            parameter_id=parameter_id,
            sensor_number=sensor_number,
            maker_key=maker_key,
            maker_category=maker_category,
            description=description,
            writable=writable,
            min_value=min_value,
            max_value=max_value,
            step=step,
            digits=digits,
            unit=unit,
            raw_min=raw_min,
            raw_max=raw_max,
        ),
    )


def parameter_number(
    parameter_id: int, scale: float, **kwargs: Any
) -> NumberField[float]:
    """Create a scaled numeric field from an ECL parameter ID."""
    return register_gauge(
        parameter_address(parameter_id),
        scale,
        parameter_id=parameter_id,
        **kwargs,
    )


def parameter_temperature(
    parameter_id: int,
    scale: float = 0.1,
    *,
    step: float | int | None = None,
    unit: str = "°C",
    **kwargs: Any,
) -> NumberField[float]:
    """Create a temperature setpoint field from an ECL parameter ID.

    The ECL manual states every setpoint with the precision the controller
    stores it at: ``scale`` is ``0.1`` for a value held in tenths of a degree
    and ``1`` for a whole-degree value. The default adjustment step follows -
    half a degree for the finer values, a whole degree otherwise - which is
    what the controller's own setting wheel does.
    """
    return parameter_number(
        parameter_id,
        scale,
        step=step if step is not None else (0.5 if scale < 1 else 1),
        digits=1 if scale < 1 else 0,
        unit=unit,
        maker_category="temperature",
        **kwargs,
    )


def sensor_temperature(
    sensor_number: int,
    *,
    description: str | None = None,
    unit: str = "°C",
) -> NumberField[float]:
    """Create a measured-temperature field from an ECL sensor number ``Sn``.

    The controller reports its Pt1000 inputs in hundredths of a degree, and an
    input with nothing connected to it as :data:`NO_SENSOR_RAW`, which decodes
    to ``None``.
    """
    return register_gauge(
        sensor_address(sensor_number),
        0.01,
        signed=True,
        nan=NO_SENSOR_RAW,
        digits=1,
        unit=unit,
        sensor_number=sensor_number,
        maker_key=f"S{sensor_number}",
        maker_category="sensor",
        description=description,
    )


def _enum_validator(enum_type: type[IntEnum]) -> Callable[[Any], Any]:
    """Return a write validator accepting only members of ``enum_type``."""

    def validate(value: Any) -> Any:
        try:
            member = enum_type(value)
        except ValueError as err:
            allowed = ", ".join(m.name.lower() for m in enum_type)
            raise Ecl310ValueValidationError(
                f"{value!r} is not one of: {allowed}"
            ) from err
        return int(member)

    return validate


def register_enum(
    address: int,
    enum_type: type[IntEnum],
    *,
    parameter_id: int | None = None,
    maker_key: str | None = None,
    maker_category: str | None = None,
    description: str | None = None,
    writable: bool | Callable[[Any], Any] = False,
) -> NumberField[IntEnum]:
    """Create an enum field at a zero-based register address."""
    field: NumberField[IntEnum] = _modbus_enum(
        address,
        enum_type,
        signed=False,
        writable=_enum_validator(enum_type) if writable else False,
    )
    return attach_metadata(
        field,
        DatapointMetadata(
            value_kind="enum",
            parameter_id=parameter_id,
            maker_key=maker_key,
            maker_category=maker_category,
            description=description,
            writable=bool(writable),
            enum=EnumMetadata(
                enum_type=enum_type,
                options=tuple(
                    OptionMetadata(member.name.lower(), int(member), member.name)
                    for member in enum_type
                ),
            ),
        ),
    )


def parameter_switch(
    parameter_id: int,
    *,
    maker_key: str | None = None,
    maker_category: str | None = None,
    description: str | None = None,
    writable: bool = False,
    inverted: bool = False,
) -> NumberField[bool]:
    """Create an on/off field from an ECL parameter ID.

    ECL renders these parameters as ``OFF``/``ON`` and holds them in the
    holding register as ``0``/``1``; any other reading decodes to ``None``.
    The controller has no coil table - it answers a coil read with "illegal
    function" - so these are read and written in the register table.
    """
    field: NumberField[bool] = _modbus_boolean(
        parameter_address(parameter_id), writable=writable
    )
    return attach_metadata(
        field,
        DatapointMetadata(
            value_kind="boolean",
            parameter_id=parameter_id,
            maker_key=maker_key,
            maker_category=maker_category,
            description=description,
            writable=writable,
            boolean=BooleanMetadata(inverted=inverted),
        ),
    )


class Ecl310Component(Component):
    """One ECL sub-system: its fields plus the controller's readable ranges.

    Subclasses declare their datapoints as class attributes using the helpers
    above. The readable ranges keep the read planner from merging two fields
    across a gap the controller does not answer.
    """

    register_ranges = REGISTER_RANGES
    coil_ranges = COIL_RANGES
    max_span = MAX_BLOCK_SPAN
    max_gap = MAX_BLOCK_GAP

    def metadata_for(self, field: str) -> DatapointMetadata | None:
        """Return the neutral ECL metadata for a declared field."""
        descriptor = type(self).declared_fields.get(field)
        if descriptor is None:
            return None
        return getattr(descriptor, "ecl_metadata", None)

    def require_metadata_for(self, field: str) -> DatapointMetadata:
        """Return the metadata for a declared field, or raise."""
        metadata = self.metadata_for(field)
        if metadata is None:
            raise AttributeError(f"unknown or untyped ECL field {field!r}")
        return metadata

    @property
    def writable_field_names(self) -> tuple[str, ...]:
        """Return the declared fields this component may write to."""
        return tuple(
            name
            for name, descriptor in type(self).declared_fields.items()
            if descriptor.writable
        )

    @property
    def present_field_names(self) -> tuple[str, ...]:
        """Return the declared fields that currently hold a value."""
        return tuple(
            name
            for name in type(self).declared_fields
            if getattr(self, name) is not None
        )
