"""Remember what a setting was before it was switched off.

The controller switches many settings off by storing a special value in place
of the setting itself, so once it is off nothing on the controller remembers
what it was. The switch uses what is remembered here to switch the setting
back on, and the number shows it while the setting is off.
"""

from __future__ import annotations

from .ecl310_modbus.metadata import NumberMetadata


class SettingMemory:
    """The last value each setting had while it was on."""

    def __init__(self) -> None:
        """Start without memories."""
        self._values: dict[tuple[str, str], float] = {}

    def get(self, component: str, field: str) -> float | None:
        """Return the last value the setting had while it was on, if known."""
        return self._values.get((component, field))

    def remember(self, component: str, field: str, value: float) -> None:
        """Keep a value the setting has while it is on."""
        self._values[(component, field)] = value


def start_value(number: NumberMetadata) -> float | None:
    """Return the value a setting gets when it is switched on with no history.

    That is the factory default where it is a usable value, else the lowest
    value the setting can have besides OFF.
    """
    default, low, high = number.default_value, number.min_value, number.max_value
    if (
        default is not None
        and (low is None or default >= low)
        and (high is None or default <= high)
    ):
        return default
    return low
