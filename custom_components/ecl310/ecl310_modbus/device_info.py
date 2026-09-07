"""Controller identity.

An ECL Comfort 310 keeps its type number, firmware version and serial number
behind the M-Bus / ECL Portal interfaces rather than in the Modbus register
map this library reads, so identity here is static rather than read from the
device. It is exposed as a small object so consumers - a device registry, a CLI
banner - have one place to take it from, and so a later release can start
filling the optional fields in from the device without changing the shape of
the API.
"""

from __future__ import annotations

from dataclasses import dataclass

MANUFACTURER = "Danfoss"
MODEL = "ECL Comfort 310"


@dataclass(frozen=True)
class DeviceInformation:
    """What is known about the controller on the other end of the link."""

    manufacturer: str = MANUFACTURER
    """Controller manufacturer."""

    model: str = MODEL
    """Controller model name."""

    application: str | None = None
    """The installed application key, e.g. ``A237.1``, when it is known."""

    firmware_version: str | None = None
    """Controller firmware version, when it is known."""

    serial_number: str | None = None
    """Controller serial number, when it is known."""

    @property
    def name(self) -> str:
        """A display name combining manufacturer and model."""
        return f"{self.manufacturer} {self.model}"
