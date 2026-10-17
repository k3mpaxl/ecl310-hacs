"""What the controller says about itself: types, versions, the application.

The ECL keeps its identity in a few system parameters, described in Danfoss'
*ECL Comfort 210 / 296 / 310, communication description* (VI.LG.V5.02, §6.12)::

    PNU 8          software build number          8575
    PNU 19         code number, after "087H"      3040  -> 087H3040
    PNU 34         hardware: letter, number       0x4803 -> H.3
    PNU 35         software: major, minor         0x0138 -> 1.56
    PNU 36, 37     serial number, high and low    1, 0x0215 -> 66069
    PNU 2060       application prefix (a letter)  65 -> A
    PNU 2061       application type number        237
    PNU 2062       application sub number         1
    PNU 2063       application version            0x0400 -> V04
    PNU 2099       production year and week       0x110C -> week 12 of 2017

They are read once, not polled: none of them changes while the controller
runs. A controller that does not serve one of the groups simply leaves those
fields unknown.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from modbus_connection import ModbusConnectionError, ModbusError

from .addresses import parameter_address

if TYPE_CHECKING:
    from modbus_connection import ModbusUnit

#: Groups of adjacent system parameters, each read in one request.
SYSTEM_PARAMETER_GROUPS: tuple[tuple[int, int], ...] = (
    (8, 8),
    (19, 19),
    (34, 37),
    (2060, 2063),
    (2099, 2099),
)

#: Prefix every Danfoss order code number carries.
CODE_NUMBER_PREFIX = "087H"


def decode_version(value: int) -> str | None:
    """``major.minor`` from a two-byte version: 0x0101 is 1.01, 0x0138 is 1.56."""
    if not value:
        return None
    return f"{value >> 8}.{value & 0xFF:02d}"


def decode_hardware(value: int) -> str | None:
    """The hardware revision, a letter and a number: 0x4102 is A.2."""
    letter = value >> 8
    if not ord("A") <= letter <= ord("Z"):
        return None
    return f"{chr(letter)}.{value & 0xFF}"


def decode_production(value: int) -> tuple[int, int] | None:
    """``(year, week)`` from the production parameter: 0x0A03 is week 3, 2010."""
    year, week = value >> 8, value & 0xFF
    if not value or not 1 <= week <= 53:
        return None
    return (2000 + year, week)


@dataclass(frozen=True)
class SystemInformation:
    """The controller's identity as it reports it; unknown fields are None."""

    code_number: str | None = None
    """Order code number, e.g. ``087H3040``."""

    hardware: str | None = None
    """Hardware revision, e.g. ``H.3``."""

    software: str | None = None
    """Software (firmware) version, e.g. ``1.56``."""

    build: int | None = None
    """Software build number."""

    serial_number: str | None = None
    """Serial number."""

    production: tuple[int, int] | None = None
    """Production ``(year, week)``."""

    application: str | None = None
    """The running application, e.g. ``A237.1``."""

    application_version: int | None = None
    """The application's major version, e.g. ``4`` for V04."""

    @property
    def application_title(self) -> str | None:
        """The application as the display names it, e.g. ``A237.1 V04``."""
        if self.application is None or self.application_version is None:
            return None
        return f"{self.application} V{self.application_version:02d}"

    @property
    def profile_key(self) -> str | None:
        """The key a profile of this application carries, e.g. ``a237_1_v04``."""
        if self.application is None or self.application_version is None:
            return None
        name = self.application.replace(".", "_").lower()
        return f"{name}_v{self.application_version:02d}"

    @classmethod
    def from_registers(cls, values: dict[int, int]) -> SystemInformation:
        """Decode the system parameters, by parameter number, that were read."""

        def get(pnu: int) -> int | None:
            return values.get(pnu)

        code = get(19)
        serial_high, serial_low = get(36), get(37)
        serial = (
            (serial_high << 16) | serial_low
            if serial_high is not None and serial_low is not None
            else None
        )
        prefix, number, sub, version = get(2060), get(2061), get(2062), get(2063)
        application = None
        if (
            prefix is not None
            and ord("A") <= prefix <= ord("Z")
            and number
            and sub is not None
        ):
            application = f"{chr(prefix)}{number}" + (f".{sub}" if sub else "")
        return cls(
            code_number=f"{CODE_NUMBER_PREFIX}{code:04d}" if code else None,
            hardware=decode_hardware(get(34)) if get(34) is not None else None,
            software=decode_version(get(35)) if get(35) is not None else None,
            build=get(8) or None,
            serial_number=str(serial) if serial else None,
            production=(
                decode_production(get(2099)) if get(2099) is not None else None
            ),
            application=application,
            application_version=(
                version >> 8 if application is not None and version else None
            ),
        )


async def async_read_system_information(unit: ModbusUnit) -> SystemInformation:
    """Read the system parameters from the controller on ``unit``.

    A group the controller refuses or does not answer is left out; a link that
    is down raises.
    """
    values: dict[int, int] = {}
    for first, last in SYSTEM_PARAMETER_GROUPS:
        try:
            read = await unit.read_holding_registers(
                parameter_address(first), last - first + 1
            )
        except ModbusConnectionError:
            raise
        except ModbusError:
            continue  # refused or unanswered: leave these fields unknown
        values.update(zip(range(first, last + 1), read, strict=False))
    return SystemInformation.from_registers(values)
