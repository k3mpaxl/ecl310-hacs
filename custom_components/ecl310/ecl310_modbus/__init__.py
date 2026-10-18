"""ecl310-modbus - read a Danfoss ECL Comfort 310 heating controller over Modbus.

Construct ``Ecl310(unit)`` with a ``modbus_connection.ModbusUnit``, call
``await device.async_update()``, then read its sub-systems as normal Python
objects::

    device.sensors.outdoor_temperature
    device.heating.comfort_setpoint
    device.hot_water.setpoint

Sub-systems live in :mod:`ecl310_modbus.subsystems`. Address helpers, the
neutral datapoint metadata and the static configuration tables live in
:mod:`ecl310_modbus.addresses`, :mod:`ecl310_modbus.metadata` and
:mod:`ecl310_modbus.configurations`.
"""

from .addresses import (
    END_OF_DAY,
    PERIODS,
    from_hours_minutes,
    parameter_address,
    parameter_range,
    period_parameter,
    schedule_ranges,
    sensor_address,
    sensor_range,
    to_hours_minutes,
)
from .applications import (
    PROFILES,
    ApplicationProfile,
    Detection,
    Parameter,
)
from .configurations import (
    COIL_RANGES,
    REGISTER_RANGES,
    RELAY_ASSIGNMENTS,
    SENSOR_ASSIGNMENTS,
    OutputAssignment,
    SensorAssignment,
)
from .data_model import Ecl310Component
from .device_info import MANUFACTURER, MODEL, DeviceInformation
from .ecl310 import (
    ALL_COMPONENT_NAMES,
    COMPONENT_NAMES,
    DEFAULT_CIRCUITS,
    DEFAULT_UNIT_ID,
    SCHEDULE_COMPONENT_NAMES,
    Circuit,
    Ecl310,
    UpdateReport,
    circuits_of,
)
from .enums import CircuitState, OperatingMode, OutputControl, Weekday
from .exceptions import (
    Ecl310Error,
    Ecl310ValueValidationError,
    Ecl310WriteNotSupportedError,
)
from .metadata import (
    BooleanMetadata,
    DatapointMetadata,
    EnumMetadata,
    NumberMetadata,
    OptionMetadata,
)
from .subsystems import (
    HeatingCircuit,
    HeatingSchedule,
    HotWater,
    HotWaterSchedule,
    Outputs,
    Schedule,
    Sensors,
)
from .system_info import SystemInformation, async_read_system_information

__all__ = [
    "ALL_COMPONENT_NAMES",
    "COIL_RANGES",
    "COMPONENT_NAMES",
    "DEFAULT_CIRCUITS",
    "DEFAULT_UNIT_ID",
    "END_OF_DAY",
    "MANUFACTURER",
    "MODEL",
    "PERIODS",
    "PROFILES",
    "REGISTER_RANGES",
    "RELAY_ASSIGNMENTS",
    "SCHEDULE_COMPONENT_NAMES",
    "SENSOR_ASSIGNMENTS",
    "ApplicationProfile",
    "BooleanMetadata",
    "Circuit",
    "CircuitState",
    "DatapointMetadata",
    "Detection",
    "DeviceInformation",
    "Ecl310",
    "Ecl310Component",
    "Ecl310Error",
    "Ecl310ValueValidationError",
    "Ecl310WriteNotSupportedError",
    "EnumMetadata",
    "HeatingCircuit",
    "HeatingSchedule",
    "HotWater",
    "HotWaterSchedule",
    "NumberMetadata",
    "OperatingMode",
    "OptionMetadata",
    "OutputAssignment",
    "OutputControl",
    "Outputs",
    "Parameter",
    "Schedule",
    "SensorAssignment",
    "Sensors",
    "SystemInformation",
    "UpdateReport",
    "Weekday",
    "async_read_system_information",
    "circuits_of",
    "from_hours_minutes",
    "parameter_address",
    "parameter_range",
    "period_parameter",
    "schedule_ranges",
    "sensor_address",
    "sensor_range",
    "to_hours_minutes",
]
