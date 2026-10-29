"""Read the ECL alarm masks and their application-specific contexts.

Danfoss communication description AQ074886472234de-000601, section 6.10.
The manual lists clear registers but does not specify a safe write protocol.
"""

from ..addresses import parameter_address, parameter_range
from ..data_model import Ecl310Component, register_integer


def _fields() -> dict:
    fields = {
        "__module__": __name__,
        "__doc__": "The two alarm masks and the 32 raw alarm contexts.",
        "register_ranges": (parameter_range(1024, 1025), parameter_range(1040, 1071)),
        "mask_high": register_integer(parameter_address(1024), signed=False),
        "mask_low": register_integer(parameter_address(1025), signed=False),
    }
    fields.update({f"context_{n}": register_integer(parameter_address(1039 + n), signed=False) for n in range(1, 33)})
    return fields


Alarms = type("Alarms", (Ecl310Component,), _fields())


def active_alarm_ids(low: int | None, high: int | None) -> list[int] | None:
    """Decode the masks, or return unknown if either mask is missing."""
    if low is None or high is None:
        return None
    return [n for n in range(1, 33) if (low if n <= 16 else high) & (1 << ((n - 1) % 16))]
