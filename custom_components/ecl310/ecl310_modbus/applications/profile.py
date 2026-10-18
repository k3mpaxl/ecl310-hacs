"""What an ECL application has: its parameters, with their domains.

An ECL Comfort 310 runs one *application* - A237.1, A337.2 and so on - and the
application decides which parameters the controller serves. A parameter the
application does not have is refused over Modbus, and with it any block read
that reaches across it. A profile lists the parameters of one application and
version, so the library reads only those, and a consumer creates only the
datapoints that exist.

Profiles are generated from Danfoss' ECL Tool reports by
``scripts/import-ecl-tool``; see :mod:`ecl310_modbus.applications.catalog`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Parameter:
    """One parameter of an application, as the controller stores it.

    ``minimum``, ``maximum`` and ``default`` are raw register values; divide
    by ``scale`` for the value the display shows.
    """

    group: str
    """The ECL Tool's group, suffixed with the circuit: ``Anti-bacteria_2``."""

    name: str
    """The parameter's name in the ECL Tool."""

    type: str
    """The register's data type: ``UI8``, ``I16``, ``UI16`` ..."""

    scale: int
    """The divisor from the raw register value to the displayed value."""

    unit: str | None
    """The unit the display shows, if any."""

    minimum: int | None
    """Lowest raw value the controller accepts."""

    maximum: int | None
    """Highest raw value the controller accepts."""

    default: int | None
    """Raw factory default."""

    writable: bool
    """Whether the parameter may be written."""

    off: int | None = None
    """A raw value the controller stores to mean "off", if the parameter has one."""

    circuit: int = 0
    """The circuit the parameter belongs to: ``1`` heating, ``2`` hot water, ...;
    ``0`` for controller-wide settings."""

    name_de: str | None = None
    """The controller display's German text for the parameter, if known."""

    options: Mapping[int, str] | None = None
    """Raw values and what they mean, when the report lists them."""

    def display_name(self, language: str | None) -> str:
        """The parameter's display text in ``language``, English otherwise."""
        if language and language.lower().startswith("de") and self.name_de:
            return self.name_de
        return self.name


@dataclass(frozen=True)
class ApplicationProfile:
    """The parameters of one ECL application and version."""

    key: str
    """Identifier, e.g. ``a337_2_v02``."""

    application: str
    """The application, as the controller's display names it: ``A337.2``."""

    version: int
    """The application version."""

    ecl_types: tuple[int, ...]
    """The ECL controllers the application runs on, e.g. ``(310,)``."""

    parameters: Mapping[int, Parameter]
    """Every parameter of the application, by ECL parameter number."""

    sensors: Mapping[int, str] | None = None
    """What each sensor input measures, by input number, as the
    :class:`~ecl310_modbus.subsystems.Sensors` field it is read into. ``None``
    for the A237/A337 assignment the library started out with."""

    relays: Mapping[int, str] | None = None
    """What each relay drives, by relay number. ``None`` for the A237/A337
    assignment; empty when the application's assignment is not known yet."""

    @property
    def title(self) -> str:
        """Display name, e.g. ``A337.2 V02``."""
        return f"{self.application} V{self.version:02d}"

    def has(self, parameter_id: int) -> bool:
        """Return whether the application has ECL parameter ``parameter_id``."""
        return parameter_id in self.parameters
