"""Exceptions raised by ecl310-modbus."""

from __future__ import annotations


class Ecl310Error(Exception):
    """Base class for every error raised by this library."""


class Ecl310ValueValidationError(Ecl310Error, ValueError):
    """Raised when a value is outside the domain the controller accepts."""


class Ecl310WriteNotSupportedError(Ecl310Error, AttributeError):
    """Raised when a datapoint that is not writable is written to."""
