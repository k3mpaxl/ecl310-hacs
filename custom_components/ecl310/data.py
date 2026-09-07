"""Runtime data for the Danfoss ECL Comfort 310 custom integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modbus_connection import ModbusConnection

    from .coordinator import Ecl310Coordinator


@dataclass
class Ecl310Data:
    """What one config entry keeps alive while it is loaded."""

    coordinator: Ecl310Coordinator
    """The coordinator polling the controller."""

    connection: ModbusConnection
    """The Modbus link this entry owns and closes when it unloads."""
