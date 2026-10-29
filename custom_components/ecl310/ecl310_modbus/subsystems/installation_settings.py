"""Explicitly model the installation settings named in issue 47.

Bounds are verified against supported reports and rebound to the active
profile when a circuit is constructed. OFF values come from Danfoss guides.
"""

from __future__ import annotations

from modbus_connection.model import NumberField

from ..data_model import parameter_number

# function: raw min, raw max, OFF sentinel, unit
INSTALLER_NUMBERS: dict[int, tuple[int, int, int | None, str | None]] = {
    77: (-11, 20, -11, "°C"),
    78: (5, 80, None, "°C"),
    79: (10, 110, None, "°C"),
    80: (5, 250, None, "s"),
    147: (0, 30, 0, "K"),
    148: (0, 30, 0, "K"),
    149: (1, 99, None, "min"),
    150: (10, 50, None, "°C"),
    174: (9, 59, 9, "min"),
    184: (5, 250, None, "K"),
    185: (1, 999, None, "s"),
    186: (5, 250, None, "s"),
    187: (1, 9, None, "K"),
    189: (2, 50, None, None),
    392: (1, 12, None, None),
    393: (1, 31, None, None),
    395: (0, 300, 0, None),
    396: (1, 12, None, None),
    397: (1, 31, None, None),
    398: (0, 50, 0, "°C"),
    399: (0, 300, 0, None),
    637: (0, 240, None, "s"),
}

INSTALLER_NUMERIC_FIELDS = frozenset({
    "pump_frost_threshold", "pump_heat_threshold", "valve_motor_protection",
    "valve_proportional_band", "valve_integral_time", "valve_running_time",
    "valve_neutral_zone", "valve_minimum_pulse", "summer_start_month",
    "summer_start_day", "summer_filter", "winter_start_month", "winter_start_day",
    "winter_cut_off", "winter_filter", "alarm_max_flow", "alarm_flow_delay_seconds",
    "alarm_flow_upper_difference", "alarm_flow_lower_difference", "alarm_flow_difference_delay",
    "alarm_flow_monitor_threshold", "alarm_input_delay",
})
INSTALLER_SWITCH_FIELDS = frozenset({"pump_exercise", "valve_exercise", "actuator_type", "alarm_input_polarity"})


def installation_number(pnu: int) -> NumberField[float]:
    """Build a known field; its exact limits are rebound from its profile."""
    raw_min, raw_max, off, unit = INSTALLER_NUMBERS[pnu % 1000]
    minimum = raw_min + 1 if off == raw_min else raw_min
    return parameter_number(
        pnu, 1, signed=raw_min < 0, min_value=minimum, max_value=raw_max,
        raw_min=raw_min, raw_max=raw_max, off_value=off, step=1, digits=0,
        unit=unit, writable=True, maker_category="circuit",
    )
