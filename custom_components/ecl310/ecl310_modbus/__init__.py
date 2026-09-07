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
    DEFAULT_UNIT_ID,
    SCHEDULE_COMPONENT_NAMES,
    Ecl310,
    UpdateReport,
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

__all__ = [
    "to_hours_minutes",
    "schedule_ranges",
    "period_parameter",
    "from_hours_minutes",
    "Weekday",
    "Schedule",
    "HotWaterSchedule",
    "HeatingSchedule",
    "SCHEDULE_COMPONENT_NAMES",
    "PERIODS",
    "END_OF_DAY",
    "ALL_COMPONENT_NAMES",
    "COIL_RANGES",
    "COMPONENT_NAMES",
    "DEFAULT_UNIT_ID",
    "MANUFACTURER",
    "MODEL",
    "REGISTER_RANGES",
    "RELAY_ASSIGNMENTS",
    "SENSOR_ASSIGNMENTS",
    "BooleanMetadata",
    "CircuitState",
    "DatapointMetadata",
    "DeviceInformation",
    "Ecl310",
    "Ecl310Component",
    "Ecl310Error",
    "Ecl310ValueValidationError",
    "Ecl310WriteNotSupportedError",
    "EnumMetadata",
    "HeatingCircuit",
    "HotWater",
    "NumberMetadata",
    "OperatingMode",
    "OptionMetadata",
    "OutputAssignment",
    "OutputControl",
    "Outputs",
    "SensorAssignment",
    "Sensors",
    "UpdateReport",
    "parameter_address",
    "parameter_range",
    "sensor_address",
    "sensor_range",
]
