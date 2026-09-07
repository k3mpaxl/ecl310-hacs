"""The address blocks the controller answers.

An ECL controller refuses a read that reaches outside a block it serves, and
the whole read fails - not just the offending register. The modelling layer
therefore needs to know where the blocks are, so it never merges two fields
across a gap the controller does not answer.

The ranges below cover exactly the datapoints this library models. They are
stated as inclusive ``(low, high)`` zero-based register addresses and handed to
every component through :class:`~ecl310_modbus.data_model.Ecl310Component`.
"""

from __future__ import annotations

from ..addresses import parameter_range, schedule_ranges, sensor_range

Range = tuple[int, int]

#: Output states and what the controller's display forced them to: six triacs
#: (3999..4004), six relays (4005..4010), and the relays' manual registers
#: (4025..4030). The controller serves the whole span, so it is one block.
OUTPUT_RANGE: Range = (3999, 4030)

#: The relays' override registers (4065..4070) - the only writable output
#: registers. They sit in a block of their own; 4031..4058 is not served for
#: this controller's fit-out, so they cannot be merged with the states.
OUTPUT_OVERRIDE_RANGE: Range = (4065, 4070)

#: Circuit operating modes: 4200 heating, 4201 hot water. The controller
#: refuses a read that reaches past 4201 - registers 4202..4209 are not served
#: - so the modes and the statuses below cannot be fetched as one block.
CIRCUIT_MODE_RANGE: Range = (4200, 4201)

#: Circuit status, one register per control circuit: 4210 heating,
#: 4211 hot water, 4212..4215 the circuits this application does not use.
CIRCUIT_STATUS_RANGE: Range = (4210, 4215)

#: Physical sensor inputs. The controller serves S1..S16 as one block and
#: refuses the register below S1.
SENSOR_RANGE: Range = sensor_range(1, 16)

#: Heating circuit setting: "Pumpe HK Aus" (ECL parameter 11021).
HEATING_PUMP_RANGE: Range = parameter_range(11021, 11021)

#: Heating circuit: return temperature limit (ECL parameter 11028).
HEATING_RETURN_LIMIT_RANGE: Range = parameter_range(11028, 11028)

#: Heating circuit: pump post-run time (ECL parameter 11040).
HEATING_POST_RUN_RANGE: Range = parameter_range(11040, 11040)

#: Heating circuit: hot water priority (ECL parameter 11052).
HEATING_PRIORITY_RANGE: Range = parameter_range(11052, 11052)

#: Heating circuit: frost protection temperature (ECL parameter 11093).
HEATING_FROST_RANGE: Range = parameter_range(11093, 11093)

#: Heating circuit: the heat curve slope (ECL parameter 11175). Register
#: 11175 - one past it - is not served, so it cannot join the setpoints below
#: however close they look.
HEATING_CURVE_SLOPE_RANGE: Range = parameter_range(11175, 11175)

#: Heating circuit settings the controller serves as one block: minimum flow
#: temperature (11177), maximum flow temperature (11178), summer cut-off
#: (11179), comfort setpoint (11180) and setback setpoint (11181).
HEATING_SETPOINT_RANGE: Range = parameter_range(11177, 11181)

#: Heating circuit: the six heat curve points Y1..Y6 (11400..11405).
HEATING_CURVE_RANGE: Range = parameter_range(11400, 11405)

#: Hot water: return temperature limit (ECL parameter 12030).
HOT_WATER_RETURN_LIMIT_RANGE: Range = parameter_range(12030, 12030)

#: Hot water: circulation pump frost temperature (ECL parameter 12076).
HOT_WATER_CIRCULATION_FROST_RANGE: Range = parameter_range(12076, 12076)

#: Hot water: frost protection temperature (ECL parameter 12093).
HOT_WATER_FROST_RANGE: Range = parameter_range(12093, 12093)

#: Hot water disinfection: weekdays (12122), start time (12123), duration
#: (12124) and setpoint (12125), which the controller serves as one block.
HOT_WATER_DISINFECTION_RANGE: Range = parameter_range(12122, 12125)

#: Hot water: maximum charging temperature (ECL parameter 12152).
HOT_WATER_CHARGE_LIMIT_RANGE: Range = parameter_range(12152, 12152)

#: Hot water comfort (12190) and setback (12191) setpoints.
HOT_WATER_SETPOINT_RANGE: Range = parameter_range(12190, 12191)

#: Hot water charging thresholds: charge (12193), stop (12194) and start
#: (12195) difference.
HOT_WATER_CHARGE_DIFFERENCE_RANGE: Range = parameter_range(12193, 12195)

#: The weekly programs, one block per weekday: the four registers between one
#: day and the next are not served, so they cannot be read as one span.
HEATING_SCHEDULE_RANGES: tuple[Range, ...] = schedule_ranges(1)
HOT_WATER_SCHEDULE_RANGES: tuple[Range, ...] = schedule_ranges(2)

#: Every holding-register block this library reads, ascending.
REGISTER_RANGES: tuple[Range, ...] = (
    *HEATING_SCHEDULE_RANGES,
    *HOT_WATER_SCHEDULE_RANGES,
    OUTPUT_RANGE,
    OUTPUT_OVERRIDE_RANGE,
    CIRCUIT_MODE_RANGE,
    CIRCUIT_STATUS_RANGE,
    SENSOR_RANGE,
    HEATING_PUMP_RANGE,
    HEATING_RETURN_LIMIT_RANGE,
    HEATING_POST_RUN_RANGE,
    HEATING_PRIORITY_RANGE,
    HEATING_FROST_RANGE,
    HEATING_CURVE_SLOPE_RANGE,
    HEATING_SETPOINT_RANGE,
    HEATING_CURVE_RANGE,
    HOT_WATER_RETURN_LIMIT_RANGE,
    HOT_WATER_CIRCULATION_FROST_RANGE,
    HOT_WATER_FROST_RANGE,
    HOT_WATER_DISINFECTION_RANGE,
    HOT_WATER_CHARGE_LIMIT_RANGE,
    HOT_WATER_SETPOINT_RANGE,
    HOT_WATER_CHARGE_DIFFERENCE_RANGE,
)

#: The library reads no coils; every ECL datapoint it models is a register.
COIL_RANGES: tuple[Range, ...] = ()


def is_span_readable(
    address: int,
    count: int,
    ranges: tuple[Range, ...],
) -> bool:
    """Return whether ``count`` registers from ``address`` sit inside one range."""
    if count < 1:
        raise ValueError(f"A span covers at least one register, got {count}")
    last = address + count - 1
    return any(low <= address and last <= high for low, high in ranges)
