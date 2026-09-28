"""Constants for the Danfoss ECL Comfort 310 custom integration."""

from datetime import timedelta
from logging import Logger, getLogger
from typing import Final

from .ecl310_modbus import OperatingMode

LOGGER: Logger = getLogger(__package__)

DOMAIN: Final = "ecl310"

CONF_UNIT_ID: Final = "unit_id"
CONF_FRAMER: Final = "framer"

DEFAULT_PORT: Final = 502
DEFAULT_UNIT_ID: Final = 1
DEFAULT_FRAMER: Final = "socket"

FRAMERS: Final = ["socket", "rtu"]

# A heating controller changes slowly, and every poll is twenty-two short
# block reads over a link that may be shared with other devices.
SCAN_INTERVAL: Final = timedelta(seconds=30)

# The weekly programs cost fourteen further reads and nothing but an operator
# changes them, so they are refreshed once every this many polls - and always
# right after one of them is written.
SCHEDULE_REFRESH_EVERY: Final = 10

# The library sub-systems, used as the report names entity availability keys on.
COMPONENT_SENSORS: Final = "sensors"
COMPONENT_HEATING: Final = "heating"
COMPONENT_HOT_WATER: Final = "hot_water"
COMPONENT_OUTPUTS: Final = "outputs"
COMPONENT_HEATING_SCHEDULE: Final = "heating_schedule"
COMPONENT_HOT_WATER_SCHEDULE: Final = "hot_water_schedule"

#: The operating modes Home Assistant may put a circuit into. Manual is not one
#: of them. Selecting it at the controller deactivates every control loop,
#: turns the frost protection off and refuses the output override this
#: integration writes - and it puts *all* circuits into manual, not the one it
#: was chosen for. It stays readable: a controller someone put into manual at
#: its own display says so, and the mode list grows to include it for exactly
#: as long as that is true.
SETTABLE_MODES: Final[tuple[OperatingMode, ...]] = (
    OperatingMode.SCHEDULED,
    OperatingMode.COMFORT,
    OperatingMode.SETBACK,
    OperatingMode.FROST_PROTECTION,
)
