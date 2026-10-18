"""Sub-systems for any circuit, not only the one they are declared for.

Danfoss numbers every circuit's parameters alike: the last three digits say
what a parameter is, the thousands which circuit it belongs to. The summer
cut-off is 11179 on circuit 1 and 12179 on circuit 2 - the manuals write it
``1x179``. The circuit's mode and status registers follow the circuit number
(4200 + n - 1, 4210 + n - 1), and its weekly program sits at ``3n10``.

:class:`~ecl310_modbus.subsystems.HeatingCircuit` is declared for circuit 1 and
:class:`~ecl310_modbus.subsystems.HotWater` for circuit 2, the A237/A337
layout. :func:`circuit_component` moves either to another circuit: a subclass
with every field at that circuit's address, and the readable ranges moved
along. An application with two heating circuits or hot water on circuit 3
(A367.1) needs nothing else.
"""

from __future__ import annotations

import copy
import dataclasses
from typing import Any

from ..addresses import parameter_address, schedule_ranges
from ..data_model import Ecl310Component
from .heating_circuit import HeatingCircuit
from .hot_water import HotWater
from .schedule import HeatingSchedule, HotWaterSchedule, Schedule, build_schedule

#: The circuit kinds, and the sub-system each is read by.
HEATING = "heating"
HOT_WATER = "hot_water"
CIRCUIT_TYPES: dict[str, type[Ecl310Component]] = {
    HEATING: HeatingCircuit,
    HOT_WATER: HotWater,
}

#: The circuit each sub-system's fields are declared at.
HOME_CIRCUIT: dict[type[Ecl310Component], int] = {HeatingCircuit: 1, HotWater: 2}

#: The per-circuit mode (4200..4205) and status (4210..4215) registers.
CIRCUIT_REGISTERS = range(4200, 4216)

#: Parameters one circuit apart are this far apart.
CIRCUIT_STRIDE = 1000

#: What a circuit aims for at a sensor is that sensor's *reference*,
#: ``1n250 + x`` for input ``Sx`` on circuit ``n``: 11253 is circuit 1's desired
#: flow at S3, 12252 circuit 2's return limit at S2 (VI.LG.V5.02, 9.1).
REFERENCE_BASE = 10250

#: The reference fields, and the sensor role whose reference each reads.
REFERENCE_ROLES: dict[str, dict[str, str]] = {
    HEATING: {
        "desired_flow_temperature": "flow_temperature",
        "return_limit_in_force": "return_temperature",
    },
    HOT_WATER: {
        "desired_flow_temperature": "hot_water_flow_temperature",
        "desired_tank_temperature": "storage_temperature",
    },
}


def reference_parameter(circuit: int, sensor: int) -> int:
    """The parameter holding circuit ``circuit``'s reference for input ``sensor``."""
    return REFERENCE_BASE + CIRCUIT_STRIDE * circuit + sensor


def _at_parameter(field: Any, parameter: int) -> Any:
    """A copy of ``field`` reading parameter ``parameter``."""
    moved = copy.copy(field)
    moved.address = parameter_address(parameter)
    moved.ecl_metadata = dataclasses.replace(field.ecl_metadata, parameter_id=parameter)
    return moved


def _moved(field: Any, shift: int) -> Any:
    """A copy of ``field`` ``shift`` circuits further on."""
    metadata = field.ecl_metadata
    moved = copy.copy(field)
    if metadata.parameter_id is not None:
        return _at_parameter(field, metadata.parameter_id + CIRCUIT_STRIDE * shift)
    if field.address in CIRCUIT_REGISTERS:
        moved.address = field.address + shift
    else:
        raise ValueError(f"{field.name} is not tied to a circuit")
    return moved


def circuit_component(
    kind_type: type[Ecl310Component],
    circuit: int,
    sensors: dict[str, int] | None = None,
) -> type[Ecl310Component]:
    """Return ``kind_type`` reading circuit ``circuit`` instead of its own.

    ``sensors`` names the inputs this circuit's sensor roles are on; a
    reference field then reads that input's reference - the desired flow of a
    second heating circuit measured at S4 is 12254, not 12253.
    """
    home = HOME_CIRCUIT[kind_type]
    shift = circuit - home
    namespace: dict[str, Any] = {}
    shifts: dict[int, int] = {}
    references = {
        name: reference_parameter(circuit, sensors[role])
        for name, role in REFERENCE_ROLES.get(_kind(kind_type), {}).items()
        if sensors and role in sensors
    }
    for name, field in kind_type.declared_fields.items():
        moved = _moved(field, shift) if shift else field
        if name in references and moved.ecl_metadata.parameter_id != references[name]:
            moved = _at_parameter(field, references[name])
        if moved is not field:
            namespace[name] = moved
            shifts[field.address] = moved.address - field.address
    if not namespace:
        return kind_type
    # Each field's readable block, moved with it. Blocks of other sub-systems
    # are left out: they would overlap the moved ones and are never read here.
    ranges: set[tuple[int, int]] = set()
    for name, field in kind_type.declared_fields.items():
        delta = shifts.get(field.address, 0) if name in namespace else 0
        low, high = next(
            (
                (low, high)
                for low, high in kind_type.register_ranges or ()
                if low <= field.address <= high
            ),
            (field.address, field.address),
        )
        ranges.add((low + delta, high + delta))
    namespace["register_ranges"] = tuple(sorted(ranges))
    namespace["CIRCUIT"] = circuit
    namespace["__doc__"] = f"{kind_type.__doc__} On ECL circuit {circuit}."
    return type(f"{kind_type.__name__}{circuit}", (kind_type,), namespace)


def _kind(kind_type: type[Ecl310Component]) -> str:
    """The circuit kind ``kind_type`` reads."""
    return next(kind for kind, known in CIRCUIT_TYPES.items() if known is kind_type)


def schedule_component(circuit: int) -> type[Schedule]:
    """Return the weekly program of circuit ``circuit``."""
    known: dict[int, type[Schedule]] = {1: HeatingSchedule, 2: HotWaterSchedule}
    if circuit in known:
        return known[circuit]
    schedule = build_schedule(f"Schedule{circuit}", circuit)
    schedule.register_ranges = tuple(
        sorted({*(schedule.register_ranges or ()), *schedule_ranges(circuit)})
    )
    return schedule
