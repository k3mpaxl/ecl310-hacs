"""Read the four limiter words described by Danfoss, section 6.17."""

from functools import lru_cache

from ..addresses import parameter_address, parameter_range
from ..data_model import Ecl310Component, register_integer

BASES = {1: 4220, 2: 4224, 3: 4228, 4: 4232, 5: 4246, 6: 4250}
WORDS = (
    (
        "return_limit",
        "room_limit",
        "wind",
        "compensation_1",
        "compensation_2",
        None,
        "parallel_priority",
        "flow_power_limit",
    ),
    (
        "holiday",
        "external_override",
        "eca_override",
        "disinfection",
        "boost",
        "ramp",
        "slave_request",
        "heating_off",
    ),
    (
        "hot_water_priority",
        "hot_water_influence",
        "scada_offset",
        "scada_hot_water_override",
        "external_setpoint",
        "external_stop",
        "fan_stop",
        "external_on",
    ),
    (
        "timeout_override",
        "output_temperature_stop",
        "floor_drying",
        "low_flow",
        None,
        None,
        None,
        None,
    ),
)
DIRECTIONS = ("none", "higher", "lower", "changed")


@lru_cache(maxsize=None)
def limiter_component(circuit: int) -> type[Ecl310Component]:
    """Create the four register descriptors for one ECL circuit."""
    base = BASES[circuit]
    fields = {
        "__module__": __name__,
        "__doc__": f"Limiter status words for circuit {circuit}.",
        "register_ranges": (parameter_range(base, base + 3),),
    }
    fields.update(
        {
            f"word_{i}": register_integer(parameter_address(base + i - 1), signed=False)
            for i in range(1, 5)
        }
    )
    return type(f"Limiter{circuit}", (Ecl310Component,), fields)


def decode_limiter(
    words: tuple[int, int, int, int], firmware: str | None, build: int | None
) -> dict[str, str | None] | None:
    """Decode known pairs; leave unsupported firmware-specific flags unknown."""
    try:
        version = tuple(int(part) for part in firmware.split(".")) if firmware else ()
        if len(version) != 2 or version < (1, 32):
            return None
    except ValueError:
        return None
    result = {}
    for word_index, names in enumerate(WORDS):
        for pair, name in enumerate(names):
            if name is None:
                continue
            supported = True
            if word_index == 3:
                if pair == 0:
                    supported = version >= (1, 54)
                elif pair in (1, 2):
                    supported = version >= (1, 56)
                elif pair == 3:
                    supported = version > (1, 58) or (
                        version == (1, 58) and build is not None and build >= 8389
                    )
            result[name] = (
                DIRECTIONS[(words[word_index] >> (pair * 2)) & 3] if supported else None
            )
    return result
