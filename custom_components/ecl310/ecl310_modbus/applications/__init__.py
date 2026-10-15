"""The ECL applications this library knows, and how to tell them apart.

Each profile lists the parameters one application and version has - see
:mod:`~ecl310_modbus.applications.profile`. Hand one to
:class:`~ecl310_modbus.Ecl310` and the device reads only those, or let
:meth:`~ecl310_modbus.Ecl310.async_detect_application` pick one.
"""

from .catalog import PROFILES
from .detection import Detection, async_detect, distinguishing_parameters
from .profile import ApplicationProfile, Parameter

__all__ = [
    "PROFILES",
    "ApplicationProfile",
    "Detection",
    "Parameter",
    "async_detect",
    "distinguishing_parameters",
]
