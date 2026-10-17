"""Controller identity, for a device registry or a CLI banner.

Manufacturer and model are static. The rest is filled in from what the
controller reports about itself (see :mod:`ecl310_modbus.system_info`) once
:meth:`~ecl310_modbus.Ecl310.async_read_system_information` has run, and stays
None where it does not report it.
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
    """The application, e.g. ``A237.1 V04``: as reported, else as configured."""

    firmware_version: str | None = None
    """Controller software version, e.g. ``1.56``, when it is known."""

    serial_number: str | None = None
    """Controller serial number, when it is known."""

    hardware_version: str | None = None
    """Controller hardware revision, e.g. ``H.3``, when it is known."""

    code_number: str | None = None
    """Order code number, e.g. ``087H3040``, when it is known."""

    production: tuple[int, int] | None = None
    """Production ``(year, week)``, when it is known."""

    @property
    def name(self) -> str:
        """A display name combining manufacturer and model."""
        return f"{self.manufacturer} {self.model}"
